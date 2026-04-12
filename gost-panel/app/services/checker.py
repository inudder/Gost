from __future__ import annotations

import asyncio
import json
import socket
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Check, Node, Settings
from app.models.enums import CheckStatus, FailedStage
from app.services.settings_service import get_settings
from app.utils.net import extract_ip, is_ip_address


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def elapsed_ms(start_time: float) -> int:
    return max(int((time.perf_counter() - start_time) * 1000), 0)


class CheckExecutionResult:
    def __init__(
        self,
        *,
        node_id: int,
        status: str,
        started_at: datetime,
        finished_at: datetime,
        failed_stage: str | None = None,
        latency_ms: int | None = None,
        egress_ip: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        raw_result: dict[str, Any] | None = None,
    ) -> None:
        self.node_id = node_id
        self.status = status
        self.started_at = started_at
        self.finished_at = finished_at
        self.failed_stage = failed_stage
        self.latency_ms = latency_ms
        self.egress_ip = egress_ip
        self.error_code = error_code
        self.error_message = error_message
        self.raw_result = raw_result or {}

    @property
    def is_success(self) -> bool:
        return self.status in {CheckStatus.ONLINE.value, CheckStatus.DEGRADED.value}


class CheckFailure(RuntimeError):
    def __init__(
        self,
        *,
        status: CheckStatus,
        failed_stage: FailedStage | None,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.failed_stage = failed_stage.value if failed_stage else None
        self.error_code = error_code
        self.message = message


class CheckerService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def check_node(self, node_id: int) -> CheckExecutionResult | None:
        async with self.session_factory() as session:
            node = await session.get(Node, node_id)
            if node is None:
                return None

            settings = await get_settings(session)
            result = await execute_check(node, settings)
            await persist_check_result(session, node, result)
            return result


async def persist_check_result(
    session: AsyncSession,
    node: Node,
    result: CheckExecutionResult,
) -> CheckExecutionResult:
    check = Check(
        node_id=node.id,
        started_at=result.started_at,
        finished_at=result.finished_at,
        status=result.status,
        failed_stage=result.failed_stage,
        latency_ms=result.latency_ms,
        egress_ip=result.egress_ip,
        error_code=result.error_code,
        error_message=result.error_message,
        raw_result_json=json.dumps(result.raw_result, ensure_ascii=False, default=str),
    )
    session.add(check)

    node.current_status = result.status
    node.last_check_started_at = result.started_at
    node.last_check_finished_at = result.finished_at
    node.last_latency_ms = result.latency_ms
    node.last_egress_ip = result.egress_ip
    node.last_error_code = result.error_code
    node.last_error_message = result.error_message
    node.last_failed_stage = result.failed_stage

    if result.is_success:
        node.last_success_at = result.finished_at
        node.fail_streak = 0
    else:
        node.fail_streak += 1

    await session.commit()
    return result


async def execute_check(node: Node, settings: Settings) -> CheckExecutionResult:
    started_at = utcnow()
    total_started = time.perf_counter()
    stage_metrics: dict[str, Any] = {
        "node": {
            "id": node.id,
            "name": node.name,
            "protocol": node.protocol,
            "host": node.host,
            "port": node.port,
        }
    }
    timeout_seconds = max((node.timeout_override_ms or settings.default_timeout_ms) / 1000, 0.5)

    try:
        stage_metrics["resolve"] = await resolve_probe(node.host, timeout_seconds)
        stage_metrics["tcp_connect"] = await tcp_connect_probe(node.host, node.port, timeout_seconds)

        if node.protocol.lower() not in {"socks5", "socks", "socks5h"}:
            final_status = (
                CheckStatus.DEGRADED.value
                if stage_metrics["tcp_connect"]["duration_ms"] > settings.degrade_latency_ms
                else CheckStatus.ONLINE.value
            )
            finished_at = utcnow()
            return CheckExecutionResult(
                node_id=node.id,
                status=final_status,
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=elapsed_ms(total_started),
                raw_result={
                    **stage_metrics,
                    "note": f"Protocol {node.protocol} uses TCP-only active probe in MVP.",
                },
            )

        stage_metrics["socks5_handshake"] = await socks5_handshake_probe(
            node.host,
            node.port,
            node.username,
            node.password,
            timeout_seconds,
        )

        test_endpoint = node.test_url_override or settings.test_endpoint
        proxy_url = build_proxy_url(node)
        stage_metrics["http_test"] = await http_probe_via_proxy(
            proxy_url=proxy_url,
            url=test_endpoint,
            timeout_seconds=timeout_seconds,
            expect_ip=False,
        )
        ip_probe = await http_probe_via_proxy(
            proxy_url=proxy_url,
            url=settings.egress_ip_endpoint,
            timeout_seconds=timeout_seconds,
            expect_ip=True,
        )
        stage_metrics["egress_ip"] = ip_probe

        total_latency = elapsed_ms(total_started)
        final_status = (
            CheckStatus.DEGRADED.value
            if total_latency > settings.degrade_latency_ms or not ip_probe.get("ip")
            else CheckStatus.ONLINE.value
        )
        finished_at = utcnow()
        error_code = None
        error_message = None
        if final_status == CheckStatus.DEGRADED.value and not ip_probe.get("ip"):
            error_code = "IP_PARSE_FAILED"
            error_message = "HTTP egress succeeded, but the external IP endpoint returned no parseable IP."

        return CheckExecutionResult(
            node_id=node.id,
            status=final_status,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=total_latency,
            egress_ip=ip_probe.get("ip"),
            error_code=error_code,
            error_message=error_message,
            raw_result=stage_metrics,
        )
    except CheckFailure as exc:
        finished_at = utcnow()
        return CheckExecutionResult(
            node_id=node.id,
            status=exc.status.value,
            started_at=started_at,
            finished_at=finished_at,
            failed_stage=exc.failed_stage,
            latency_ms=elapsed_ms(total_started),
            error_code=exc.error_code,
            error_message=exc.message,
            raw_result=stage_metrics,
        )


async def resolve_probe(host: str, timeout_seconds: float) -> dict[str, Any]:
    probe_started = time.perf_counter()
    if is_ip_address(host):
        return {"duration_ms": 0, "addresses": [host], "source": "literal"}

    loop = asyncio.get_running_loop()
    try:
        info = await asyncio.wait_for(
            loop.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise CheckFailure(
            status=CheckStatus.TIMEOUT,
            failed_stage=FailedStage.RESOLVE,
            error_code="DNS_TIMEOUT",
            message=f"DNS lookup timed out for {host}.",
        ) from exc
    except socket.gaierror as exc:
        raise CheckFailure(
            status=CheckStatus.DNS_FAILED,
            failed_stage=FailedStage.RESOLVE,
            error_code="DNS_RESOLVE_FAILED",
            message=f"DNS lookup failed for {host}: {exc}.",
        ) from exc

    addresses = sorted({entry[4][0] for entry in info})
    return {"duration_ms": elapsed_ms(probe_started), "addresses": addresses, "source": "dns"}


async def tcp_connect_probe(host: str, port: int, timeout_seconds: float) -> dict[str, Any]:
    probe_started = time.perf_counter()
    reader = None
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise CheckFailure(
            status=CheckStatus.TIMEOUT,
            failed_stage=FailedStage.TCP_CONNECT,
            error_code="TCP_TIMEOUT",
            message=f"TCP connect timed out for {host}:{port}.",
        ) from exc
    except OSError as exc:
        raise CheckFailure(
            status=CheckStatus.CONNECT_FAILED,
            failed_stage=FailedStage.TCP_CONNECT,
            error_code="TCP_CONNECT_FAILED",
            message=f"TCP connect failed for {host}:{port}: {exc}.",
        ) from exc
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    return {"duration_ms": elapsed_ms(probe_started)}


async def socks5_handshake_probe(
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    probe_started = time.perf_counter()
    reader = None
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout_seconds)
        writer.write(build_greeting_packet(username))
        await asyncio.wait_for(writer.drain(), timeout=timeout_seconds)
        version, method = await asyncio.wait_for(reader.readexactly(2), timeout=timeout_seconds)

        if version != 5:
            raise CheckFailure(
                status=CheckStatus.HANDSHAKE_FAILED,
                failed_stage=FailedStage.SOCKS5_HANDSHAKE,
                error_code="SOCKS_BAD_VERSION",
                message=f"SOCKS5 server returned unexpected version {version}.",
            )
        if method == 0xFF:
            raise CheckFailure(
                status=CheckStatus.AUTH_FAILED if username else CheckStatus.HANDSHAKE_FAILED,
                failed_stage=FailedStage.SOCKS5_AUTH if username else FailedStage.SOCKS5_HANDSHAKE,
                error_code="SOCKS_METHOD_REJECTED",
                message="SOCKS5 server rejected all authentication methods.",
            )
        if username:
            if method != 0x02:
                raise CheckFailure(
                    status=CheckStatus.AUTH_FAILED,
                    failed_stage=FailedStage.SOCKS5_AUTH,
                    error_code="SOCKS_AUTH_METHOD",
                    message="SOCKS5 server did not select username/password authentication.",
                )
            writer.write(build_auth_packet(username, password or ""))
            await asyncio.wait_for(writer.drain(), timeout=timeout_seconds)
            auth_version, auth_status = await asyncio.wait_for(
                reader.readexactly(2),
                timeout=timeout_seconds,
            )
            if auth_version != 1 or auth_status != 0x00:
                raise CheckFailure(
                    status=CheckStatus.AUTH_FAILED,
                    failed_stage=FailedStage.SOCKS5_AUTH,
                    error_code="SOCKS_AUTH_REJECTED",
                    message="SOCKS5 authentication was rejected.",
                )
        elif method != 0x00:
            raise CheckFailure(
                status=CheckStatus.HANDSHAKE_FAILED,
                failed_stage=FailedStage.SOCKS5_HANDSHAKE,
                error_code="SOCKS_UNEXPECTED_METHOD",
                message=f"SOCKS5 server selected unexpected method {method}.",
            )
    except asyncio.TimeoutError as exc:
        raise CheckFailure(
            status=CheckStatus.TIMEOUT,
            failed_stage=FailedStage.SOCKS5_AUTH if username else FailedStage.SOCKS5_HANDSHAKE,
            error_code="SOCKS_TIMEOUT",
            message="SOCKS5 handshake timed out.",
        ) from exc
    except OSError as exc:
        raise CheckFailure(
            status=CheckStatus.HANDSHAKE_FAILED,
            failed_stage=FailedStage.SOCKS5_HANDSHAKE,
            error_code="SOCKS_IO_ERROR",
            message=f"SOCKS5 handshake failed: {exc}.",
        ) from exc
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    return {"duration_ms": elapsed_ms(probe_started)}


def build_proxy_url(node: Node) -> str:
    credentials = ""
    if node.username:
        credentials = f"{quote(node.username, safe='')}:{quote(node.password or '', safe='')}@"
    return f"socks5://{credentials}{node.host}:{node.port}"


def build_greeting_packet(username: str | None) -> bytes:
    return b"\x05\x01\x02" if username else b"\x05\x01\x00"


def build_auth_packet(username: str, password: str) -> bytes:
    username_bytes = username.encode("utf-8")
    password_bytes = password.encode("utf-8")
    return (
        b"\x01"
        + bytes([len(username_bytes)])
        + username_bytes
        + bytes([len(password_bytes)])
        + password_bytes
    )


async def http_probe_via_proxy(
    *,
    proxy_url: str,
    url: str,
    timeout_seconds: float,
    expect_ip: bool,
) -> dict[str, Any]:
    probe_started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            trust_env=False,
        ) as client:
            response = await client.get(url, headers={"User-Agent": "GOST-Panel/0.1"})
    except httpx.TimeoutException as exc:
        raise CheckFailure(
            status=CheckStatus.TIMEOUT,
            failed_stage=FailedStage.EGRESS_IP if expect_ip else FailedStage.HTTP_TEST,
            error_code="HTTP_TIMEOUT",
            message=f"HTTP probe to {url} timed out.",
        ) from exc
    except httpx.HTTPError as exc:
        raise CheckFailure(
            status=CheckStatus.EGRESS_FAILED,
            failed_stage=FailedStage.EGRESS_IP if expect_ip else FailedStage.HTTP_TEST,
            error_code="HTTP_PROXY_ERROR",
            message=f"HTTP probe to {url} failed: {exc}.",
        ) from exc

    duration = elapsed_ms(probe_started)
    result = {
        "duration_ms": duration,
        "url": url,
        "status_code": response.status_code,
        "ok": response.status_code < 400,
        "headers": dict(response.headers),
    }
    if not result["ok"]:
        raise CheckFailure(
            status=CheckStatus.EGRESS_FAILED,
            failed_stage=FailedStage.EGRESS_IP if expect_ip else FailedStage.HTTP_TEST,
            error_code=f"HTTP_{response.status_code}",
            message=f"HTTP probe to {url} returned status {response.status_code}.",
        )

    if expect_ip:
        text_body = response.text
        ip = None
        if "json" in response.headers.get("content-type", ""):
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if isinstance(payload, dict):
                for key in ("ip", "origin", "address"):
                    candidate = payload.get(key)
                    if isinstance(candidate, str):
                        ip = extract_ip(candidate)
                        if ip:
                            break
        if ip is None:
            ip = extract_ip(text_body)
        result["ip"] = ip
        result["body"] = text_body[:200]

    return result
