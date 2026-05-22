from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import Settings

_LOG = structlog.get_logger(__name__)


class JobScheduler:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._scheduler = AsyncIOScheduler()

    def add_cron_job(
        self,
        job_id: str,
        func: Callable[..., Awaitable[Any]],
        hour: int,
        minute: int,
    ) -> None:
        trigger = CronTrigger(hour=hour, minute=minute)
        self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
        )
        _LOG.info("SCHEDULER_JOB_REGISTERED", job_id=job_id, hour=hour, minute=minute)

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            _LOG.info("SCHEDULER_STARTED")

    def shutdown(self, wait: bool = True) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            _LOG.info("SCHEDULER_STOPPED")
