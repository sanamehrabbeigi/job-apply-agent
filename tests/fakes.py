"""Shared test doubles for the job search code. No network, no Claude."""

from __future__ import annotations

from datetime import datetime

from job_apply_agent.db import Database
from job_apply_agent.preferences import merge_defaults
from job_apply_agent.search.base import SourceContext
from job_apply_agent.search.filters import role_matches
from job_apply_agent.search.http import HttpError
from job_apply_agent.search.quota import QuotaGuard, budgets_from_prefs


class FakeHttp:
    """Answers requests from ``routes``: {url_prefix: json/text value or Exception}. First matching prefix wins."""

    def __init__(self, routes: dict[str, object] | None = None):
        self.routes = routes or {}
        self.calls: list[tuple] = []

    def _answer(self, url: str):
        for prefix, value in self.routes.items():
            if url.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value
        raise HttpError(404, url)

    async def get_json(self, url, *, params=None, headers=None, retry_429=True):
        self.calls.append(("GET", url, params, headers))
        return self._answer(url)

    async def post_json(self, url, body, *, headers=None, retry_429=True):
        self.calls.append(("POST", url, body, headers))
        return self._answer(url)

    async def get_text(self, url, *, params=None, headers=None, retry_429=True):
        self.calls.append(("GET", url, params, headers))
        return self._answer(url)


def make_ctx(*, prefs=None, companies=(), routes=None, env=None, known=(), last_success=None, db=None,
             now: datetime | None = None) -> SourceContext:
    prefs = merge_defaults(prefs or {})
    db = db or Database(":memory:")
    known_set = set(known)
    quota_kwargs = {"now_fn": (lambda: now)} if now else {}
    return SourceContext(
        prefs=prefs,
        companies=list(companies),
        http=FakeHttp(routes),
        quota=QuotaGuard(db, budgets_from_prefs(prefs), **quota_kwargs),
        env=env or {},
        role_ok=lambda title: role_matches(title, prefs["role_terms"]),
        known=lambda source, external_id: (source, external_id) in known_set,
        last_success=lambda source: (last_success or {}).get(source),
        progress=lambda _msg: None,
    )
