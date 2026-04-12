from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config.settings import BASE_DIR, get_app_settings
from app.db.migrations import run_migrations
from app.db.session import get_engine, get_sessionmaker, init_db
from app.routes import dashboard, gost, health, nodes, settings
from app.services.checker import CheckerService
from app.services.scheduler import SchedulerService
from app.services.settings_service import ensure_app_settings
from app.utils.templates import create_templates


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app_settings = get_app_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(app_settings.database_url)
    engine = get_engine()
    await run_migrations(engine)
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        await ensure_app_settings(session, app_settings)

    checker = CheckerService(session_factory)
    scheduler = SchedulerService(session_factory, checker)
    app.state.templates = create_templates(app_settings)
    app.state.checker = checker
    app.state.scheduler = scheduler

    scheduler.start()
    yield
    await scheduler.stop()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=Path(BASE_DIR, "app", "static")), name="static")
    app.include_router(health.router)
    app.include_router(dashboard.router)
    app.include_router(gost.router)
    app.include_router(nodes.router)
    app.include_router(settings.router)
    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=app_settings.bind_host,
        port=app_settings.bind_port,
        reload=app_settings.debug,
    )


if __name__ == "__main__":
    run()
