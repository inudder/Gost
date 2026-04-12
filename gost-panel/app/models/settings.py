from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    panel_host: Mapped[str] = mapped_column(String(255), default="127.0.0.1")
    panel_port: Mapped[int] = mapped_column(Integer, default=17777)
    gost_api_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gost_api_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gost_api_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    test_endpoint: Mapped[str] = mapped_column(String(500), default="http://httpbin.org/status/204")
    egress_ip_endpoint: Mapped[str] = mapped_column(String(500), default="http://api.ipify.org")
    default_timeout_ms: Mapped[int] = mapped_column(Integer, default=6000)
    polling_interval_sec: Mapped[int] = mapped_column(Integer, default=120)
    max_concurrent_checks: Mapped[int] = mapped_column(Integer, default=10)
    degrade_latency_ms: Mapped[int] = mapped_column(Integer, default=1500)
    last_global_check_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_global_check_finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_gost_poll_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_gost_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
