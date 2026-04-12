from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.routes.helpers import get_templates
from app.services.dashboard_service import get_dashboard_data


router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    templates = get_templates(request)
    context = await get_dashboard_data(session)
    context.update({"request": request, "page_name": "dashboard"})
    return templates.TemplateResponse(request=request, name="dashboard.html", context=context)


@router.get("/partials/dashboard", response_class=HTMLResponse)
async def dashboard_partial(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    templates = get_templates(request)
    context = await get_dashboard_data(session)
    context.update({"request": request})
    return templates.TemplateResponse(
        request=request,
        name="partials/dashboard_content.html",
        context=context,
    )
