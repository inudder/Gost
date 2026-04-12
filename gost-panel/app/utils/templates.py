from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config.settings import AppSettings, BASE_DIR


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def format_latency(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value} ms"


def status_badge_class(value: str | None) -> str:
    mapping = {
        "online": "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
        "degraded": "bg-amber-500/15 text-amber-200 ring-amber-500/30",
        "timeout": "bg-orange-500/15 text-orange-200 ring-orange-500/30",
        "offline": "bg-rose-500/15 text-rose-200 ring-rose-500/30",
        "dns_failed": "bg-rose-500/15 text-rose-200 ring-rose-500/30",
        "connect_failed": "bg-rose-500/15 text-rose-200 ring-rose-500/30",
        "auth_failed": "bg-rose-500/15 text-rose-200 ring-rose-500/30",
        "handshake_failed": "bg-rose-500/15 text-rose-200 ring-rose-500/30",
        "egress_failed": "bg-rose-500/15 text-rose-200 ring-rose-500/30",
        "unknown": "bg-slate-500/15 text-slate-200 ring-slate-500/30",
    }
    return mapping.get(value or "unknown", mapping["unknown"])


def create_templates(settings: AppSettings) -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(Path(BASE_DIR, "app", "templates")))
    templates.env.auto_reload = settings.template_auto_reload
    templates.env.filters["datetime"] = format_datetime
    templates.env.filters["latency"] = format_latency
    templates.env.globals["status_badge_class"] = status_badge_class
    templates.env.globals["app_title"] = settings.app_name
    return templates
