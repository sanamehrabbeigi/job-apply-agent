"""Builds the long-lived app objects (database, search runner, scheduler) from the data folder."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from . import paths
from .career_profile import load_answers, load_profile
from .db import Database
from .documents import read_resume
from .envfile import load_env
from .preferences import load_preferences, resume_path
from .search.companies import load_companies
from .search.events import EventBus
from .search.http import Http
from .search.pipeline import CandidateDocs, SearchRunner
from .search.scheduler import Scheduler
from .timeutil import now_utc


@dataclass
class Runtime:
    db: Database
    events: EventBus
    runner: SearchRunner
    scheduler: Scheduler
    now: Callable[[], datetime]


def default_http() -> Http:
    return Http(host_delays={"www.linkedin.com": (3.0, 6.0)})


def load_candidate_docs() -> CandidateDocs | None:
    path = resume_path(load_preferences())
    if not path.is_file():
        return None
    return CandidateDocs(
        resume=read_resume(path),
        profile=load_profile(paths.profile_dir()),
        answers=load_answers(paths.profile_dir()),
    )


def build_runtime(*, db: Database | None = None, sources=None, scorer=None, http_factory=None,
                  now_fn: Callable[[], datetime] = now_utc) -> Runtime:
    db = db or Database(paths.db_path())
    events = EventBus()
    runner = SearchRunner(
        db,
        events=events,
        load_prefs=load_preferences,
        load_companies=load_companies,
        load_env=load_env,
        load_docs=load_candidate_docs,
        http_factory=http_factory or default_http,
        scorer=scorer,
        sources=sources,
        now_fn=now_fn,
    )
    scheduler = Scheduler(runner, db, load_preferences, now_fn=now_fn)
    return Runtime(db=db, events=events, runner=runner, scheduler=scheduler, now=now_fn)
