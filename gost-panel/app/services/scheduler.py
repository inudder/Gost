from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Node
from app.services.checker import CheckerService
from app.services.gost_sync import poll_gost_services
from app.services.settings_service import get_settings


logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SchedulerService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        checker: CheckerService,
    ) -> None:
        self.session_factory = session_factory
        self.checker = checker
        self._runner_task: asyncio.Task[None] | None = None
        self._manual_cycle_task: asyncio.Task[bool] | None = None
        self._stop_event = asyncio.Event()
        self._cycle_lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._cycle_lock.locked() or (
            self._manual_cycle_task is not None and not self._manual_cycle_task.done()
        )

    def start(self) -> None:
        if self._runner_task is None:
            self._runner_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._runner_task is not None:
            await self._runner_task
        if self._manual_cycle_task is not None and not self._manual_cycle_task.done():
            await self._manual_cycle_task

    def trigger_manual_cycle(self) -> bool:
        if self.is_running:
            return False
        self._manual_cycle_task = asyncio.create_task(self.run_full_cycle(origin="manual"))
        return True

    async def poll_gost_once(self) -> tuple[bool, str | None]:
        if self._cycle_lock.locked():
            return False, "Check cycle is already running."

        async with self._cycle_lock:
            async with self.session_factory() as session:
                settings = await get_settings(session)
                return await poll_gost_services(session, settings)

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_full_cycle(origin="scheduled")
            except Exception:  # pragma: no cover
                logger.exception("Background scheduler cycle failed.")

            interval = await self._load_interval()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _load_interval(self) -> int:
        async with self.session_factory() as session:
            settings = await get_settings(session)
            return settings.polling_interval_sec

    async def run_full_cycle(self, *, origin: str) -> bool:
        if self._cycle_lock.locked():
            return False

        async with self._cycle_lock:
            async with self.session_factory() as session:
                settings = await get_settings(session)
                settings.last_global_check_started_at = utcnow()
                await session.commit()

                await poll_gost_services(session, settings)
                concurrency = settings.max_concurrent_checks
                result = await session.execute(select(Node.id).where(Node.enabled.is_(True)))
                node_ids = list(result.scalars().all())

            semaphore = asyncio.Semaphore(concurrency)

            async def run_single(node_id: int) -> None:
                async with semaphore:
                    try:
                        await self.checker.check_node(node_id)
                    except Exception:  # pragma: no cover
                        logger.exception("Node check failed for node_id=%s during %s cycle.", node_id, origin)

            await asyncio.gather(*(run_single(node_id) for node_id in node_ids))

            async with self.session_factory() as session:
                settings = await get_settings(session)
                settings.last_global_check_finished_at = utcnow()
                await session.commit()
        return True
