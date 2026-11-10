"""Resume tailoring started from the browser. The agent's questions wait for answers from the UI."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import paths
from .db import Database
from .jobs import JobFetchError, JobPosting, fetch_job
from .preferences import resume_path
from .search.events import EventBus
from .tailor_flow import TailorRequest, run_tailor_flow

MIN_FULL_DESCRIPTION = 300


class MissingResume(RuntimeError):
    pass


class NotWaiting(RuntimeError):
    pass


@dataclass
class TailorSession:
    id: str
    job_id: int
    state: str = "running"  # running | waiting | done | error
    questions: list[str] = field(default_factory=list)
    progress: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    answers_future: asyncio.Future | None = None
    task: asyncio.Task | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "job_id": self.job_id, "state": self.state, "questions": self.questions,
                "progress": self.progress[-20:], "result": self.result, "error": self.error}


class TailorManager:
    def __init__(self, db: Database, events: EventBus, *, load_prefs: Callable[[], dict[str, Any]],
                 answer_timeout: float = 1800, flow=run_tailor_flow, fetch=fetch_job):
        self.db = db
        self.events = events
        self.load_prefs = load_prefs
        self.answer_timeout = answer_timeout
        self.flow = flow
        self.fetch = fetch
        self.sessions: dict[str, TailorSession] = {}

    def latest_for_job(self, job_id: int) -> TailorSession | None:
        for session in reversed(self.sessions.values()):
            if session.job_id == job_id:
                return session
        return None

    def start(self, job_id: int) -> TailorSession:
        """Start tailoring for a job, or return the run already in progress for it."""
        job = self.db.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        active = self.latest_for_job(job_id)
        if active is not None and active.state in ("running", "waiting"):
            return active
        prefs = self.load_prefs()
        resume = resume_path(prefs)
        if not resume.is_file():
            raise MissingResume("Add your master resume in Settings first.")
        session = TailorSession(id=uuid.uuid4().hex[:12], job_id=job_id)
        self.sessions[session.id] = session
        session.task = asyncio.create_task(self._run(session, job, prefs, resume))
        return session

    async def wait(self, session_id: str) -> None:
        task = self.sessions[session_id].task
        if task:
            await task

    def answer(self, session_id: str, answers: list[tuple[str, str]]) -> None:
        session = self.sessions[session_id]
        if session.state != "waiting" or session.answers_future is None or session.answers_future.done():
            raise NotWaiting("This tailoring run isn't waiting for answers.")
        session.answers_future.set_result([(q, a.strip()) for q, a in answers if a and a.strip()])

    # --- internals -------------------------------------------------------------------------

    def _publish(self, session: TailorSession, kind: str) -> None:
        self.events.publish({"type": f"tailor.{kind}", "session": session.to_dict()})

    def _note(self, session: TailorSession, message: str) -> None:
        session.progress.append(message)
        del session.progress[:-50]
        self._publish(session, "progress")

    async def _ask(self, session: TailorSession, questions: list[str]) -> list[tuple[str, str]]:
        session.questions = list(questions)
        session.state = "waiting"
        session.answers_future = asyncio.get_running_loop().create_future()
        self._publish(session, "questions")
        try:
            answers = await asyncio.wait_for(session.answers_future, self.answer_timeout)
        except asyncio.TimeoutError:
            answers = []
            self._note(session, "No answers within the time limit; finishing with the current version.")
        session.state, session.questions, session.answers_future = "running", [], None
        return answers

    async def _job_input(self, job: dict[str, Any]) -> tuple[str | None, str | None]:
        url = job["links"][0]["url"] if job["links"] else ""
        posting = JobPosting(url=url, title=job["title"], company=job["company"], location=job["location"],
                             description=job["description"])
        if not job["description_is_partial"] and len(job["description"]) >= MIN_FULL_DESCRIPTION:
            return posting.to_text(), None
        try:
            full = await asyncio.to_thread(self.fetch, url)
            return full.to_text(), None
        except (JobFetchError, ValueError, OSError):
            if job["description"]:
                return posting.to_text(), None
            return None, url or None

    async def _run(self, session: TailorSession, job: dict[str, Any], prefs: dict[str, Any], resume) -> None:
        try:
            job_text, job_url = await self._job_input(job)
            if not job_text and not job_url:
                raise RuntimeError("This job has no description or link to tailor against.")
            out_dir = paths.output_dir()
            req = TailorRequest(
                resume_path=resume, job_text=job_text, job_url=job_url, profile_dir=paths.profile_dir(),
                target_score=prefs["target_score"], max_rounds=3, model=prefs["models"]["tailoring"],
                formats=["md", "docx", "pdf"], out_dir=out_dir,
            )
            outcome = await self.flow(
                req,
                ask=lambda questions: self._ask(session, questions),
                progress=lambda message: self._note(session, message),
                status=lambda message: self._note(session, message),
            )
            root = out_dir.resolve()
            folder = os.path.relpath(outcome.folder.resolve(), root).replace(os.sep, "/")
            session.result = {
                "match_score": outcome.tailored.match_score,
                "job_title": outcome.tailored.job_title,
                "company": outcome.tailored.company,
                "missing_keywords": outcome.tailored.missing_keywords,
                "files": [os.path.relpath(p.resolve(), root).replace(os.sep, "/") for p in outcome.files],
                "warnings": outcome.warnings,
                "folder": folder,
            }
            session.state = "done"
            self.db.update_job(session.job_id, tailored_folder=folder)
            self._publish(session, "done")
        except Exception as exc:  # noqa: BLE001 - shown in the job panel
            session.state = "error"
            session.error = str(exc) or exc.__class__.__name__
            self._publish(session, "error")
