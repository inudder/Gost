from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models import GostService
from app.routes.helpers import get_scheduler, get_templates, is_htmx
from app.services.scheduler import SchedulerService
from app.services.settings_service import get_settings


router = APIRouter(prefix="/gost", tags=["gost"])


async def build_gost_context(session: AsyncSession) -> dict[str, object]:
    settings = await get_settings(session)
    services = list(
        (
            await session.execute(select(GostService).order_by(GostService.service_name.asc()))
        ).scalars()
    )
    return {"settings": settings, "services": services}


@router.get("", response_class=HTMLResponse)
async def gost_page(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    templates = get_templates(request)
    context = await build_gost_context(session)
    context.update({"request": request, "page_name": "gost", "message": None})
    return templates.TemplateResponse(request=request, name="gost/index.html", context=context)


@router.get("/partials/panel", response_class=HTMLResponse)
async def gost_panel_partial(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    templates = get_templates(request)
    context = await build_gost_context(session)
    context.update({"request": request, "message": None})
    return templates.TemplateResponse(request=request, name="partials/gost_panel.html", context=context)


@router.post("/poll", response_class=HTMLResponse)
async def poll_gost(
    request: Request,
    scheduler: SchedulerService = Depends(get_scheduler),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    success, message = await scheduler.poll_gost_once()
    if not success and message is None:
        message = "GOST API poll failed."

    if is_htmx(request):
        templates = get_templates(request)
        context = await build_gost_context(session)
        context.update({"request": request, "message": message or "GOST API poll finished."})
        return templates.TemplateResponse(
            request=request,
            name="partials/gost_panel.html",
            context=context,
        )

    return RedirectResponse(url="/gost", status_code=303)
