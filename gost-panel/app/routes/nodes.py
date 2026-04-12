from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.routes.helpers import get_checker, get_scheduler, get_templates, is_htmx
from app.schemas.node import NodeForm
from app.services.checker import CheckerService
from app.services.node_service import (
    create_node,
    delete_node,
    get_node,
    get_node_metrics,
    get_recent_checks,
    list_nodes,
    toggle_node_enabled,
    update_node,
)
from app.services.scheduler import SchedulerService


router = APIRouter(prefix="/nodes", tags=["nodes"])


async def render_nodes_table(
    request: Request,
    session: AsyncSession,
    *,
    message: str | None = None,
    status: str | None = None,
) -> Response:
    templates = get_templates(request)
    nodes = await list_nodes(session, status=status)
    return templates.TemplateResponse(
        request=request,
        name="partials/nodes_table.html",
        context={
            "request": request,
            "nodes": nodes,
            "message": message,
        },
    )


def build_node_form_payload(
    *,
    name: str,
    protocol: str,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    notes: str | None,
    tags: str | None,
    enabled: bool,
    test_url_override: str | None,
    timeout_override_ms: int | None,
) -> NodeForm:
    return NodeForm.model_validate(
        {
            "name": name,
            "protocol": protocol,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "notes": notes,
            "tags": tags,
            "enabled": enabled,
            "test_url_override": test_url_override,
            "timeout_override_ms": timeout_override_ms,
        }
    )


@router.get("", response_class=HTMLResponse)
async def nodes_page(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    templates = get_templates(request)
    nodes = await list_nodes(session)
    return templates.TemplateResponse(
        request=request,
        name="nodes/index.html",
        context={
            "request": request,
            "page_name": "nodes",
            "nodes": nodes,
        },
    )


@router.get("/table", response_class=HTMLResponse)
async def nodes_table(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    status: str | None = Query(default=None),
) -> HTMLResponse:
    return await render_nodes_table(request, session, status=status)


@router.get("/new", response_class=HTMLResponse)
async def new_node_form(request: Request) -> Response:
    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="nodes/form.html",
        context={
            "request": request,
            "page_name": "nodes",
            "mode": "create",
            "node": None,
            "errors": [],
        },
    )


@router.post("", response_class=HTMLResponse)
async def create_node_route(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    name: str = Form(...),
    protocol: str = Form(default="socks5"),
    host: str = Form(...),
    port: int = Form(...),
    username: str | None = Form(default=None),
    password: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    enabled: bool = Form(default=False),
    test_url_override: str | None = Form(default=None),
    timeout_override_ms: int | None = Form(default=None),
) -> Response:
    templates = get_templates(request)
    try:
        payload = build_node_form_payload(
            name=name,
            protocol=protocol,
            host=host,
            port=port,
            username=username,
            password=password,
            notes=notes,
            tags=tags,
            enabled=enabled,
            test_url_override=test_url_override,
            timeout_override_ms=timeout_override_ms,
        )
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="nodes/form.html",
            context={
                "request": request,
                "page_name": "nodes",
                "mode": "create",
                "node": None,
                "errors": exc.errors(),
            },
            status_code=422,
        )

    node = await create_node(session, payload)
    return RedirectResponse(url=f"/nodes/{node.id}", status_code=303)


@router.get("/{node_id}", response_class=HTMLResponse)
async def node_detail(
    request: Request,
    node_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    node = await get_node(session, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")

    templates = get_templates(request)
    metrics = await get_node_metrics(session, node_id)
    checks = await get_recent_checks(session, node_id)
    return templates.TemplateResponse(
        request=request,
        name="nodes/detail.html",
        context={
            "request": request,
            "page_name": "nodes",
            "node": node,
            "checks": checks,
            "metrics": metrics,
        },
    )


@router.get("/{node_id}/edit", response_class=HTMLResponse)
async def edit_node_form(
    request: Request,
    node_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    node = await get_node(session, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")

    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="nodes/form.html",
        context={
            "request": request,
            "page_name": "nodes",
            "mode": "edit",
            "node": node,
            "errors": [],
        },
    )


@router.post("/{node_id}", response_class=HTMLResponse)
async def update_node_route(
    request: Request,
    node_id: int,
    session: AsyncSession = Depends(get_db_session),
    name: str = Form(...),
    protocol: str = Form(default="socks5"),
    host: str = Form(...),
    port: int = Form(...),
    username: str | None = Form(default=None),
    password: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    enabled: bool = Form(default=False),
    test_url_override: str | None = Form(default=None),
    timeout_override_ms: int | None = Form(default=None),
) -> Response:
    node = await get_node(session, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")

    templates = get_templates(request)
    try:
        payload = build_node_form_payload(
            name=name,
            protocol=protocol,
            host=host,
            port=port,
            username=username,
            password=password,
            notes=notes,
            tags=tags,
            enabled=enabled,
            test_url_override=test_url_override,
            timeout_override_ms=timeout_override_ms,
        )
    except ValidationError as exc:
        return templates.TemplateResponse(
            request=request,
            name="nodes/form.html",
            context={
                "request": request,
                "page_name": "nodes",
                "mode": "edit",
                "node": node,
                "errors": exc.errors(),
            },
            status_code=422,
        )

    await update_node(session, node, payload)
    return RedirectResponse(url=f"/nodes/{node_id}", status_code=303)


@router.post("/{node_id}/toggle", response_class=HTMLResponse)
async def toggle_node_route(
    request: Request,
    node_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    node = await get_node(session, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")
    await toggle_node_enabled(session, node)
    if is_htmx(request):
        return await render_nodes_table(request, session, message="Node state updated.")
    return RedirectResponse(url="/nodes", status_code=303)


@router.post("/{node_id}/delete", response_class=HTMLResponse)
async def delete_node_route(
    request: Request,
    node_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    node = await get_node(session, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")
    await delete_node(session, node)
    if is_htmx(request):
        return await render_nodes_table(request, session, message="Node deleted.")
    return RedirectResponse(url="/nodes", status_code=303)


@router.post("/{node_id}/check", response_class=HTMLResponse)
async def check_node_route(
    request: Request,
    node_id: int,
    checker: CheckerService = Depends(get_checker),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    result = await checker.check_node(node_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Node not found.")
    if is_htmx(request):
        return await render_nodes_table(
            request,
            session,
            message=f"Check finished with status: {result.status}.",
        )
    return RedirectResponse(url=f"/nodes/{node_id}", status_code=303)


@router.post("/actions/check-all", response_class=HTMLResponse)
async def check_all_route(
    request: Request,
    scheduler: SchedulerService = Depends(get_scheduler),
) -> Response:
    started = scheduler.trigger_manual_cycle()
    message = "Full check cycle started." if started else "A check cycle is already running."
    if is_htmx(request):
        templates = get_templates(request)
        return templates.TemplateResponse(
            request=request,
            name="partials/alert.html",
            context={"request": request, "message": message},
        )
    return RedirectResponse(url="/nodes", status_code=303)
