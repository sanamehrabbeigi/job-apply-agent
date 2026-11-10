"""Keep paid-tier APIs inside their free quota. Counts calls per source per day or month."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from ..db import Database
from ..timeutil import now_utc


class QuotaExceeded(RuntimeError):
    pass


def period_key(period: str, now: datetime) -> str:
    return now.strftime("%Y-%m-%d") if period == "day" else now.strftime("%Y-%m")


def next_reset(period: str, now: datetime) -> date:
    if period == "day":
        return (now + timedelta(days=1)).date()
    return date(now.year + (now.month == 12), now.month % 12 + 1, 1)


def budgets_from_prefs(prefs: dict[str, Any]) -> dict[str, tuple[int, str]]:
    return {
        name: (int(cfg["budget"]), cfg.get("budget_period", "month"))
        for name, cfg in prefs["sources"].items()
        if "budget" in cfg
    }


class QuotaGuard:
    def __init__(self, db: Database, budgets: dict[str, tuple[int, str]],
                 now_fn: Callable[[], datetime] = now_utc):
        self.db = db
        self.budgets = budgets
        self.now_fn = now_fn

    def remaining(self, source: str) -> int | None:
        if source not in self.budgets:
            return None
        budget, period = self.budgets[source]
        return max(0, budget - self.db.quota_used(source, period_key(period, self.now_fn())))

    def consume(self, source: str, n: int = 1) -> None:
        left = self.remaining(source)
        if left is None:
            return
        _budget, period = self.budgets[source]
        now = self.now_fn()
        if left < n:
            raise QuotaExceeded(f"free quota reached until {next_reset(period, now)}")
        self.db.quota_add(source, period_key(period, now), n)

    def usage(self) -> dict[str, dict[str, Any]]:
        now = self.now_fn()
        return {
            source: {
                "used": self.db.quota_used(source, period_key(period, now)),
                "budget": budget,
                "period": period,
                "resets": str(next_reset(period, now)),
            }
            for source, (budget, period) in self.budgets.items()
        }
