from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Check, Node
from app.services.settings_service import get_settings


SUCCESS_STATUSES = ("online", "degraded")


async def get_dashboard_data(session: AsyncSession) -> dict[str, object]:
    settings = await get_settings(session)
    total_nodes = int(await session.scalar(select(func.count()).select_from(Node)) or 0)
    online_nodes = int(
        await session.scalar(select(func.count()).select_from(Node).where(Node.current_status == "online"))
        or 0
    )
    degraded_nodes = int(
        await session.scalar(
            select(func.count()).select_from(Node).where(Node.current_status == "degraded")
        )
        or 0
    )
    avg_latency = await session.scalar(
        select(func.avg(Node.last_latency_ms)).where(
            Node.current_status.in_(SUCCESS_STATUSES),
            Node.last_latency_ms.is_not(None),
        )
    )
    recent_errors = list(
        (
            await session.execute(
                select(Check, Node)
                .join(Node, Check.node_id == Node.id)
                .where(Check.status.notin_(SUCCESS_STATUSES))
                .order_by(Check.started_at.desc(), Check.id.desc())
                .limit(8)
            )
        ).all()
    )
    recent_checks = list(
        (
            await session.execute(
                select(Check, Node)
                .join(Node, Check.node_id == Node.id)
                .order_by(Check.started_at.desc(), Check.id.desc())
                .limit(10)
            )
        ).all()
    )

    return {
        "stats": {
            "gost_api_status": "connected"
            if settings.gost_api_url and not settings.last_gost_error
            else "error"
            if settings.gost_api_url
            else "not_configured",
            "total_nodes": total_nodes,
            "online_nodes": online_nodes,
            "offline_nodes": max(total_nodes - online_nodes - degraded_nodes, 0),
            "degraded_nodes": degraded_nodes,
            "avg_latency_ms": int(avg_latency) if avg_latency is not None else None,
            "last_global_check_at": settings.last_global_check_finished_at,
        },
        "recent_errors": recent_errors,
        "recent_checks": recent_checks,
        "settings": settings,
    }
