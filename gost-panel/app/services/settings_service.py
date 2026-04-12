from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import AppSettings
from app.models import Settings
from app.schemas.settings import SettingsForm


async def get_settings(session: AsyncSession) -> Settings:
    settings = await session.get(Settings, 1)
    if settings is None:
        settings = Settings(id=1)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings


async def ensure_app_settings(session: AsyncSession, app_settings: AppSettings) -> Settings:
    settings = await get_settings(session)
    settings.panel_host = app_settings.bind_host
    settings.panel_port = app_settings.bind_port
    await session.commit()
    await session.refresh(settings)
    return settings


async def update_settings(
    session: AsyncSession,
    payload: SettingsForm,
    *,
    keep_existing_password: bool = True,
) -> Settings:
    settings = await get_settings(session)
    settings.gost_api_url = payload.gost_api_url
    settings.gost_api_username = payload.gost_api_username
    if payload.gost_api_password or not keep_existing_password:
        settings.gost_api_password = payload.gost_api_password
    settings.test_endpoint = payload.test_endpoint
    settings.egress_ip_endpoint = payload.egress_ip_endpoint
    settings.default_timeout_ms = payload.default_timeout_ms
    settings.polling_interval_sec = payload.polling_interval_sec
    settings.max_concurrent_checks = payload.max_concurrent_checks
    settings.degrade_latency_ms = payload.degrade_latency_ms
    await session.commit()
    await session.refresh(settings)
    return settings
