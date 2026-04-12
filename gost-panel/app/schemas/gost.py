from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class GostServiceSnapshot(BaseModel):
    service_name: str = Field(min_length=1, max_length=255)
    address: str | None = None
    protocol: str | None = None
    state: str | None = None
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any], fallback_name: str) -> "GostServiceSnapshot":
        listener = payload.get("listener") or {}
        handler = payload.get("handler") or {}
        metadata = payload.get("metadata") or {}
        runtime = payload.get("runtime") or {}
        status = payload.get("status") or {}
        listener_type = listener.get("type")
        handler_type = handler.get("type")
        protocol = listener_type or handler_type or payload.get("protocol")
        if listener_type == "tcp" and handler_type in {"socks5", "auto"}:
            protocol = "socks5"
        return cls(
            service_name=str(payload.get("name") or fallback_name),
            address=payload.get("addr") or payload.get("address") or listener.get("addr"),
            protocol=protocol,
            state=payload.get("state")
            or status.get("state")
            or runtime.get("state")
            or metadata.get("state"),
            raw=payload,
        )
