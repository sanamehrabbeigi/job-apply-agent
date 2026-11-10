"""Runs each source on its own interval while the app is open (hourly company sites, daily JSearch...)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from ..db import Database
from ..preferences import SOURCE_NAMES
from ..timeutil import now_utc, parse_datetime
from .pipeline import SearchAlreadyRunning

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(
        self,
        runner,
        db: Database,
        load_prefs: Callable[[], dict[str, Any]],
        *,
        now_fn: Callable[[], datetime] = now_utc,
        tick_seconds: float = 60,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.runner = runner
        self.db = db
        self.load_prefs = load_prefs
        self.now_fn = now_fn
        self.tick_seconds = tick_seconds
        self._sleep = sleep

    def due_sources(self, now: datetime) -> list[str]:
        prefs = self.load_prefs()
        states = self.db.source_states()
        due = []
        for name in SOURCE_NAMES:
            cfg = prefs["sources"].get(name, {})
            if not cfg.get("enabled"):
                continue
            last = parse_datetime((states.get(name) or {}).get("last_attempt_at"))
            if last is None or now - last >= timedelta(hours=float(cfg["interval_hours"])):
                due.append(name)
        return due

    async def tick(self) -> int | None:
        if self.runner.running or not self.load_prefs()["schedule"]["enabled"]:
            return None
        due = self.due_sources(self.now_fn())
        if not due:
            return None
        try:
            return await self.runner.run(trigger="schedule", sources=due)
        except SearchAlreadyRunning:
            return None

    async def run_forever(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - keep the scheduler alive; the run is logged
                logger.exception("Scheduled search failed")
            await self._sleep(self.tick_seconds)
