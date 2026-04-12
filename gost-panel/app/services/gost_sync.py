from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GostService, Node, Settings
from app.models.enums import NodeSourceType
from app.schemas.gost import GostServiceSnapshot
from app.services.gost_client import GostApiClient, GostApiError
from app.utils.net import parse_host_port


async def poll_gost_services(session: AsyncSession, settings: Settings) -> tuple[bool, str | None]:
    if not settings.gost_api_url:
        settings.last_gost_error = None
        await session.commit()
        return False, "GOST API URL is not configured."

    client = GostApiClient(
        settings.gost_api_url,
        username=settings.gost_api_username,
        password=settings.gost_api_password,
        timeout=max(settings.default_timeout_ms / 1000, 2),
    )

    try:
        config_payload = await client.fetch_config()
        services_payload = await client.fetch_services()
    except GostApiError as exc:
        settings.last_gost_error = str(exc)
        await session.commit()
        return False, str(exc)

    now = datetime.now(timezone.utc)
    snapshots = [
        GostServiceSnapshot.from_payload(item, fallback_name=f"service-{index}")
        for index, item in enumerate(services_payload, start=1)
    ]
    current_names = {snapshot.service_name for snapshot in snapshots}
    imported_service_refs = {build_service_source_ref(snapshot.service_name) for snapshot in snapshots}
    chain_nodes = extract_chain_nodes(config_payload)
    imported_chain_refs = {item["source_ref"] for item in chain_nodes}

    existing_services = {
        service.service_name: service
        for service in (
            await session.execute(select(GostService).where(GostService.service_name.in_(current_names)))
        ).scalars()
    }
    existing_nodes = {
        (node.source_type, node.source_ref): node
        for node in (
            await session.execute(
                select(Node).where(
                    Node.source_type.in_(
                        [
                            NodeSourceType.GOST.value,
                            NodeSourceType.GOST_SERVICE.value,
                            NodeSourceType.GOST_CHAIN_NODE.value,
                        ]
                    )
                )
            )
        ).scalars()
    }

    for snapshot in snapshots:
        service = existing_services.get(snapshot.service_name)
        if service is None:
            service = GostService(service_name=snapshot.service_name)
            session.add(service)

        service.address = snapshot.address
        service.protocol = snapshot.protocol
        service.state = snapshot.state or "unknown"
        service.last_seen_at = now
        service.error_note = None
        service.raw_json = json.dumps(snapshot.raw, ensure_ascii=False, default=str)

        parsed = parse_host_port(snapshot.address)
        if parsed:
            host, port = parsed
            source_ref = build_service_source_ref(snapshot.service_name)
            node = existing_nodes.get((NodeSourceType.GOST_SERVICE.value, source_ref)) or existing_nodes.get(
                (NodeSourceType.GOST.value, snapshot.service_name)
            )
            if node is None:
                node = Node(
                    name=snapshot.service_name,
                    protocol=snapshot.protocol or "tcp",
                    host=host,
                    port=port,
                    source_type=NodeSourceType.GOST_SERVICE.value,
                    source_ref=source_ref,
                    enabled=True,
                    notes="Imported from GOST API",
                )
                session.add(node)
            else:
                node.name = snapshot.service_name
                node.protocol = snapshot.protocol or node.protocol
                node.host = host
                node.port = port
                node.source_type = NodeSourceType.GOST_SERVICE.value
                node.source_ref = source_ref
            node.notes = build_service_note(snapshot.raw)
            if snapshot.raw.get("handler", {}).get("auth"):
                auth = snapshot.raw["handler"]["auth"]
                node.username = auth.get("username")
                node.password = auth.get("password")

    for chain_node in chain_nodes:
        node = existing_nodes.get((NodeSourceType.GOST_CHAIN_NODE.value, chain_node["source_ref"]))
        if node is None:
            node = Node(
                name=chain_node["name"],
                protocol=chain_node["protocol"],
                host=chain_node["host"],
                port=chain_node["port"],
                source_type=NodeSourceType.GOST_CHAIN_NODE.value,
                source_ref=chain_node["source_ref"],
                enabled=True,
            )
            session.add(node)
        else:
            node.name = chain_node["name"]
            node.protocol = chain_node["protocol"]
            node.host = chain_node["host"]
            node.port = chain_node["port"]

        node.username = chain_node["username"]
        node.password = chain_node["password"]
        node.notes = chain_node["notes"]
        node.tags = chain_node["tags"]
        node.source_type = NodeSourceType.GOST_CHAIN_NODE.value
        node.source_ref = chain_node["source_ref"]

    if current_names:
        await session.execute(delete(GostService).where(GostService.service_name.notin_(current_names)))
    else:
        await session.execute(delete(GostService))

    all_imported_refs = imported_service_refs | imported_chain_refs
    if all_imported_refs:
        await session.execute(
            delete(Node).where(
                Node.source_type.in_(
                    [NodeSourceType.GOST_SERVICE.value, NodeSourceType.GOST_CHAIN_NODE.value]
                ),
                Node.source_ref.notin_(all_imported_refs),
            )
        )
    else:
        await session.execute(
            delete(Node).where(
                Node.source_type.in_(
                    [NodeSourceType.GOST_SERVICE.value, NodeSourceType.GOST_CHAIN_NODE.value]
                )
            )
        )

    settings.last_gost_poll_at = now
    settings.last_gost_error = None
    await session.commit()
    return True, None


def build_service_source_ref(service_name: str) -> str:
    return f"service:{service_name}"


def build_service_note(payload: dict[str, object]) -> str:
    listener = payload.get("listener") or {}
    handler = payload.get("handler") or {}
    return (
        f"Imported from GOST service; listener={listener.get('type', 'unknown')}; "
        f"handler={handler.get('type', 'unknown')}"
    )


def extract_chain_nodes(config_payload: dict[str, object]) -> list[dict[str, str | int | None]]:
    chains = config_payload.get("chains")
    if not isinstance(chains, list):
        return []

    collected: list[dict[str, str | int | None]] = []
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        chain_name = str(chain.get("name") or "chain")
        hops = chain.get("hops")
        if not isinstance(hops, list):
            continue

        for hop_index, hop in enumerate(hops, start=1):
            if not isinstance(hop, dict):
                continue
            hop_name = str(hop.get("name") or f"hop-{hop_index}")
            nodes = hop.get("nodes")
            if not isinstance(nodes, list):
                continue

            for node_index, item in enumerate(nodes, start=1):
                if not isinstance(item, dict):
                    continue
                addr = item.get("addr")
                parsed = parse_host_port(str(addr) if addr is not None else None)
                if not parsed:
                    continue

                host, port = parsed
                name = str(item.get("name") or f"{chain_name}-{hop_name}-node-{node_index}")
                source_ref = f"chain:{chain_name}:{hop_name}:{name}"
                connector = item.get("connector") or {}
                dialer = item.get("dialer") or {}
                auth = connector.get("auth") or {}
                protocol = infer_chain_node_protocol(connector_type=connector.get("type"), dialer_type=dialer.get("type"))
                note = (
                    f"Imported from GOST chain={chain_name}, hop={hop_name}; "
                    f"connector={connector.get('type', 'unknown')}; dialer={dialer.get('type', 'unknown')}"
                )

                collected.append(
                    {
                        "name": name,
                        "host": host,
                        "port": port,
                        "protocol": protocol,
                        "username": auth.get("username"),
                        "password": auth.get("password"),
                        "source_ref": source_ref,
                        "notes": note,
                        "tags": f"gost,{chain_name},{hop_name}",
                    }
                )
    return collected


def infer_chain_node_protocol(*, connector_type: str | None, dialer_type: str | None) -> str:
    if (dialer_type in {None, "", "tcp"}) and connector_type in {"socks5", "http"}:
        return connector_type
    return dialer_type or connector_type or "tcp"
