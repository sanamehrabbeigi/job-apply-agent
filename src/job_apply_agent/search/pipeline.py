"""One search run: fetch every source in parallel, store and dedupe, gate, then score new jobs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..db import Database
from ..jobs import JobPosting
from ..preferences import SOURCE_NAMES
from ..timeutil import iso, now_utc, parse_datetime
from .base import Source, SourceContext
from .dedupe import canonical_url, dedupe_key
from .events import EventBus
from .filters import evaluate, role_matches
from .quota import QuotaGuard, budgets_from_prefs
from .scoring import profile_hash, score_jobs

logger = logging.getLogger(__name__)


class SearchAlreadyRunning(RuntimeError):
    pass


@dataclass
class CandidateDocs:
    resume: str
    profile: str = ""
    answers: str = ""


class SearchRunner:
    def __init__(
        self,
        db: Database,
        *,
        events: EventBus,
        load_prefs: Callable[[], dict[str, Any]],
        load_companies: Callable[[], list[dict[str, Any]]],
        load_env: Callable[[], dict[str, str]],
        load_docs: Callable[[], CandidateDocs | None],
        http_factory: Callable[[], Any],
        scorer=None,
        sources: dict[str, Source] | None = None,
        now_fn: Callable[[], datetime] = now_utc,
    ):
        if sources is None:
            from .sources import SOURCES

            sources = dict(SOURCES)
        self.db = db
        self.events = events
        self.load_prefs = load_prefs
        self.load_companies = load_companies
        self.load_env = load_env
        self.load_docs = load_docs
        self.http_factory = http_factory
        self.scorer = scorer or score_jobs
        self.sources = sources
        self.now_fn = now_fn
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._lock.locked()

    async def run(self, *, trigger: str, sources: list[str] | None = None, score: bool = True) -> int:
        if self._lock.locked():
            raise SearchAlreadyRunning("A search is already running.")
        async with self._lock:
            return await self._run(trigger, sources, score)

    def _names(self, prefs: dict[str, Any], requested: list[str] | None) -> list[str]:
        if requested is None:
            return [n for n in SOURCE_NAMES if prefs["sources"].get(n, {}).get("enabled") and n in self.sources]
        unknown = [n for n in requested if n not in SOURCE_NAMES]
        if unknown:
            raise ValueError(f"Unknown source(s): {', '.join(unknown)}. Choose from {', '.join(SOURCE_NAMES)}.")
        return [n for n in requested if n in self.sources]

    async def _run(self, trigger: str, requested: list[str] | None, score: bool) -> int:
        prefs = self.load_prefs()
        names = self._names(prefs, requested)
        run_id = self.db.start_run(trigger, iso(self.now_fn()))
        self.events.publish({"type": "run.started", "run_id": run_id, "trigger": trigger, "sources": names})
        stats: dict[str, Any] = {}
        scored = 0
        error = None
        try:
            if names:
                ctx = self._context(prefs, run_id)
                await asyncio.gather(*(self._run_source(name, ctx, prefs, run_id, stats) for name in names))
            if score:
                stats["scoring"] = await self._score(prefs, run_id)
            else:
                stats["scoring"] = {"status": "skipped", "scored": 0, "message": "Scoring was turned off for this run."}
            scored = int(stats["scoring"].get("scored", 0))
        except Exception as exc:  # noqa: BLE001 - recorded on the run and shown in the UI
            logger.exception("Search run %s failed", run_id)
            error = str(exc) or exc.__class__.__name__
        finally:
            self.db.finish_run(run_id, sources=stats, scored=scored, error=error, now=iso(self.now_fn()))
            self.events.publish({"type": "run.finished", "run_id": run_id, "run": self.db.get_run(run_id)})
        return run_id

    def _context(self, prefs: dict[str, Any], run_id: int) -> SourceContext:
        states = self.db.source_states()
        return SourceContext(
            prefs=prefs,
            companies=self.load_companies(),
            http=self.http_factory(),
            quota=QuotaGuard(self.db, budgets_from_prefs(prefs), self.now_fn),
            env=self.load_env(),
            role_ok=lambda title: role_matches(title, prefs["role_terms"]),
            known=self.db.has_link,
            last_success=lambda name: parse_datetime((states.get(name) or {}).get("last_success_at")),
            progress=lambda message: self.events.publish({"type": "run.progress", "run_id": run_id, "message": message}),
        )

    async def _run_source(self, name: str, ctx: SourceContext, prefs: dict[str, Any], run_id: int,
                          stats: dict[str, Any]) -> None:
        self.events.publish({"type": "run.source", "run_id": run_id, "source": name, "stat": {"status": "running"}})
        now = iso(self.now_fn())
        try:
            result = await self.sources[name](ctx)
        except Exception as exc:  # noqa: BLE001 - one source failing must not stop the others
            logger.warning("Source %s failed: %s", name, exc)
            stats[name] = {"status": "error", "error": (str(exc) or exc.__class__.__name__)[:300]}
            self.db.mark_source_attempt(name, now, success=False)
        else:
            if result.skipped:
                stats[name] = {"status": "skipped", "reason": result.skipped}
                self.db.mark_source_attempt(name, now, success=False)
            else:
                relevant = new = 0
                for posting in result.postings:
                    posting.source = posting.source or name
                    ok, label = evaluate(posting, prefs)
                    _job_id, created = self.db.upsert_posting(
                        posting, dedupe_key=dedupe_key(posting), canonical_url=canonical_url(posting.url),
                        relevant=ok, location_label=label, run_id=run_id, now=now,
                    )
                    relevant += int(ok)
                    new += int(created and ok)
                for board, ids in result.seen_ids.items():
                    self.db.mark_missing(name, board, ids)
                stats[name] = {
                    "status": "partial" if result.warnings else "ok",
                    "fetched": len(result.postings),
                    "relevant": relevant,
                    "new": new,
                    "warnings": result.warnings[:10],
                }
                self.db.mark_source_attempt(name, now, success=True)
        self.events.publish({"type": "run.source", "run_id": run_id, "source": name, "stat": stats[name]})

    async def _score(self, prefs: dict[str, Any], run_id: int) -> dict[str, Any]:
        docs = self.load_docs()
        if docs is None:
            return {"status": "skipped", "scored": 0,
                    "message": "No resume yet, so jobs were not scored. Add it in Settings."}
        phash = profile_hash(docs.resume, docs.profile, docs.answers)
        pending = self.db.jobs_to_score(phash)
        if not pending:
            return {"status": "ok", "scored": 0, "failed": 0, "message": "Nothing new to score."}
        model = prefs["models"]["scoring"]

        def progress(done: int, total: int) -> None:
            self.events.publish({"type": "run.scoring", "run_id": run_id, "done": done, "total": total})

        progress(0, len(pending))
        outcome = await self.scorer(
            pending, resume=docs.resume, profile=docs.profile, answers=docs.answers, model=model,
            batch_size=prefs["scoring"]["batch_size"], concurrency=prefs["scoring"]["concurrency"],
            on_progress=progress,
        )
        now = iso(self.now_fn())
        for s in outcome.scores:
            self.db.save_score(s.job_id, score=s.score, summary=s.summary, reasons=s.reasons, gaps=s.gaps,
                               seniority_fit=s.seniority_fit, model=model, profile_hash=phash, now=now)
        if outcome.usage_limited:
            status, message = "limited", "Claude usage limit reached; the rest will be scored on the next run."
        elif outcome.failed:
            status, message = "partial", f"{len(outcome.failed)} job(s) couldn't be scored this time; they'll be retried."
        else:
            status, message = "ok", f"Scored {len(outcome.scores)} job(s)."
        return {"status": status, "scored": len(outcome.scores), "failed": len(outcome.failed),
                "message": message, "errors": outcome.errors[:3]}


def refilter_jobs(db: Database, prefs: dict[str, Any]) -> int:
    """Re-run the relevance gate over stored jobs after role/location/exclusion settings change."""
    changed = 0
    for job in db.all_jobs_for_refilter():
        posting = JobPosting(url="", title=job["title"], company=job["company"], location=job["location"],
                             remote=job["remote"], country=job["country"])
        ok, label = evaluate(posting, prefs)
        if ok != job["relevant"] or (ok and label != job["location_label"]):
            db.set_relevance(job["id"], ok, label)
            changed += 1
    return changed
