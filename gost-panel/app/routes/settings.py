from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.routes.helpers import get_templates
from app.schemas.settings import SettingsForm
from app.services.settings_service import get_settings, update_settings


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    templates = get_templates(request)
    settings = await get_settings(session)
    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "request": request,
            "page_name": "settings",
            "settings": settings,
            "errors": [],
        },
    )


@router.post("", response_class=HTMLResponse)
async def update_settings_page(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    gost_api_url: str | None = Form(default=None),
    gost_api_username: str | None = Form(default=None),
    gost_api_password: str | None = Form(default=None),
    test_endpoint: str = Form(...),
    egress_ip_endpoint: str = Form(...),
    default_timeout_ms: int = Form(...),
    polling_interval_sec: int = Form(...),
    max_concurrent_checks: int = Form(...),
    degrade_latency_ms: int = Form(...),
) -> Response:
    templates = get_templates(request)
    try:
        payload = SettingsForm.model_validate(
            {
                "gost_api_url": gost_api_url,
                "gost_api_username": gost_api_username,
                "gost_api_password": gost_api_password,
                "test_endpoint": test_endpoint,
                "egress_ip_endpoint": egress_ip_endpoint,
                "default_timeout_ms": default_timeout_ms,
                "polling_interval_sec": polling_interval_sec,
                "max_concurrent_checks": max_concurrent_checks,
                "degrade_latency_ms": degrade_latency_ms,
            }
        )
    except ValidationError as exc:
        settings = await get_settings(session)
        return templates.TemplateResponse(
            request=request,
            name="settings/index.html",
            context={
                "request": request,
                "page_name": "settings",
                "settings": settings,
                "errors": exc.errors(),
            },
            status_code=422,
        )

    await update_settings(session, payload, keep_existing_password=True)
    return RedirectResponse(url="/settings", status_code=303)
