from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Check, Node
from app.schemas.node import NodeForm
from app.utils.net import normalize_bind_host


def build_node_query(*, status: str | None = None, enabled: bool | None = None) -> Select[tuple[Node]]:
    query = select(Node).order_by(Node.updated_at.desc(), Node.id.desc())
    if status:
        query = query.where(Node.current_status == status)
    if enabled is not None:
        query = query.where(Node.enabled.is_(enabled))
    return query


async def list_nodes(
    session: AsyncSession,
    *,
    status: str | None = None,
    enabled: bool | None = None,
) -> list[Node]:
    result = await session.execute(build_node_query(status=status, enabled=enabled))
    return list(result.scalars().all())


async def get_node(session: AsyncSession, node_id: int) -> Node | None:
    return await session.get(Node, node_id)


async def create_node(session: AsyncSession, payload: NodeForm) -> Node:
    node = Node(
        name=payload.name,
        protocol=payload.protocol,
        host=normalize_bind_host(payload.host),
        port=payload.port,
        username=payload.username,
        password=payload.password,
        notes=payload.notes,
        tags=payload.tags,
        enabled=payload.enabled,
        test_url_override=payload.test_url_override,
        timeout_override_ms=payload.timeout_override_ms,
    )
    session.add(node)
    await session.commit()
    await session.refresh(node)
    return node


async def update_node(session: AsyncSession, node: Node, payload: NodeForm) -> Node:
    node.name = payload.name
    node.protocol = payload.protocol
    node.host = normalize_bind_host(payload.host)
    node.port = payload.port
    node.username = payload.username
    if payload.password:
        node.password = payload.password
    node.notes = payload.notes
    node.tags = payload.tags
    node.enabled = payload.enabled
    node.test_url_override = payload.test_url_override
    node.timeout_override_ms = payload.timeout_override_ms
    await session.commit()
    await session.refresh(node)
    return node


async def toggle_node_enabled(session: AsyncSession, node: Node) -> Node:
    node.enabled = not node.enabled
    await session.commit()
    await session.refresh(node)
    return node


async def delete_node(session: AsyncSession, node: Node) -> None:
    await session.delete(node)
    await session.commit()


async def get_recent_checks(session: AsyncSession, node_id: int, *, limit: int = 20) -> list[Check]:
    result = await session.execute(
        select(Check)
        .where(Check.node_id == node_id)
        .order_by(Check.started_at.desc(), Check.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_node_metrics(session: AsyncSession, node_id: int) -> dict[str, object]:
    avg_latency = await session.scalar(
        select(func.avg(Check.latency_ms)).where(
            Check.node_id == node_id,
            Check.status.in_(("online", "degraded")),
            Check.latency_ms.is_not(None),
        )
    )
    latest_check = await session.scalar(
        select(Check)
        .where(Check.node_id == node_id)
        .order_by(Check.started_at.desc(), Check.id.desc())
        .limit(1)
    )
    return {
        "avg_latency_ms": int(avg_latency) if avg_latency is not None else None,
        "latest_check": latest_check,
    }
