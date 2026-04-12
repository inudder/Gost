from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.services.checker import CheckerService
from app.services.scheduler import SchedulerService


def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def get_checker(request: Request) -> CheckerService:
    return request.app.state.checker


def get_scheduler(request: Request) -> SchedulerService:
    return request.app.state.scheduler


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"
