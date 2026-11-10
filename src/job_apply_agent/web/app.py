"""FastAPI backend for the local job app. Binds to 127.0.0.1 only (see cli.run_serve)."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import paths
from ..documents import _find_soffice
from ..envfile import load_env
from ..preferences import load_preferences, merge_defaults, resume_path, save_preferences, validate_preferences
from ..runtime import Runtime, build_runtime, default_http
from ..search.companies import load_companies, save_companies, test_company, validate_companies
from ..search.pipeline import refilter_jobs
from ..search.quota import QuotaGuard, budgets_from_prefs
from ..tailor import auth_warning
from ..tailor_sessions import MissingResume, NotWaiting
from ..timeutil import iso

STATIC_DIR = Path(__file__).with_name("static")
RESUME_SUFFIXES = {".docx", ".md", ".txt"}
PROFILE_SUFFIXES = {".docx", ".md", ".markdown", ".txt"}
Status = Literal["new", "saved", "applied", "interview", "offer", "rejected"]


class JobUpdate(BaseModel):
    status: Status | None = None
    notes: str | None = None


class SearchRequest(BaseModel):
    sources: list[str] | None = None


class Answer(BaseModel):
    question: str
    answer: str


class AnswersBody(BaseModel):
    answers: list[Answer]


def create_app(runtime: Runtime | None = None, *, start_scheduler: bool = True) -> FastAPI:
    rt = runtime or build_runtime()
    background: set[asyncio.Task] = set()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(rt.scheduler.run_forever()) if start_scheduler else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="job-apply-agent", lifespan=lifespan)
    app.state.runtime = rt

    def now() -> str:
        return iso(rt.now())

    def keep(task: asyncio.Task) -> None:
        background.add(task)
        task.add_done_callback(lambda t: (background.discard(t), t.cancelled() or t.exception()))

    # --- jobs --------------------------------------------------------------------------

    @app.get("/api/jobs")
    def list_jobs(
        tab: Literal["new", "all"] = "all",
        sort: Literal["score", "posted", "company", "title"] = "score",
        order: Literal["asc", "desc"] = "desc",
        role: str | None = None,
        location: str | None = None,
        source: str | None = None,
        status: Status | None = None,
        min_score: int | None = None,
        include_closed: bool = False,
        hide_done: bool = False,
    ) -> dict[str, Any]:
        jobs = rt.db.list_jobs(now=now(), tab=tab, sort=sort, order=order, role=role, location=location,
                               source=source, status=status, min_score=min_score, include_closed=include_closed,
                               hide_done=hide_done)
        return {"jobs": jobs, "counts": rt.db.counts(now())}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: int) -> dict[str, Any]:
        job = rt.db.get_job(job_id)
        if job is None:
            raise HTTPException(404, "Job not found.")
        return job

    @app.patch("/api/jobs/{job_id}")
    def update_job(job_id: int, body: JobUpdate) -> dict[str, Any]:
        fields = body.model_dump(exclude_none=True)
        job = rt.db.update_job(job_id, **fields)
        if job is None:
            raise HTTPException(404, "Job not found.")
        return job

    # --- search runs -------------------------------------------------------------------

    @app.post("/api/search", status_code=202)
    async def start_search(body: SearchRequest | None = None) -> dict[str, bool]:
        if rt.runner.running:
            raise HTTPException(409, "A search is already running.")
        sources = body.sources if body else None
        keep(asyncio.create_task(rt.runner.run(trigger="manual", sources=sources)))
        await asyncio.sleep(0)  # let the run take the lock before we answer
        return {"started": True}

    @app.get("/api/runs")
    def list_runs(limit: int = 10) -> list[dict[str, Any]]:
        return rt.db.list_runs(max(1, min(limit, 100)))

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int) -> dict[str, Any]:
        run = rt.db.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Run not found.")
        return run

    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        queue = rt.events.subscribe()

        async def stream():
            try:
                yield "retry: 3000\n\n"
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield f"data: {json.dumps(event)}\n\n"
            finally:
                rt.events.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # --- settings ------------------------------------------------------------------------

    @app.get("/api/preferences")
    def get_preferences() -> dict[str, Any]:
        return load_preferences()

    @app.put("/api/preferences")
    def put_preferences(body: dict[str, Any]) -> dict[str, Any]:
        try:
            prefs = validate_preferences(merge_defaults(body))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise HTTPException(422, str(exc)) from None
        old = load_preferences()
        save_preferences(prefs)
        gate_keys = ("role_terms", "locations", "excluded_companies")
        refiltered = refilter_jobs(rt.db, prefs) if any(old[k] != prefs[k] for k in gate_keys) else 0
        return {"preferences": prefs, "refiltered": refiltered}

    @app.get("/api/companies")
    def get_companies() -> list[dict[str, Any]]:
        return load_companies()

    @app.put("/api/companies")
    def put_companies(body: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            return save_companies(body)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/companies/test")
    async def check_company(body: dict[str, Any]) -> dict[str, Any]:
        try:
            validate_companies([body])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return await test_company(body, default_http())

    # --- profile -------------------------------------------------------------------------

    def profile_info() -> dict[str, Any]:
        resume = resume_path(load_preferences())
        folder = paths.profile_dir()
        documents = [
            {"name": p.name, "size": p.stat().st_size}
            for p in sorted(folder.iterdir())
            if p.is_file() and p.suffix.lower() in PROFILE_SUFFIXES
        ] if folder.is_dir() else []
        return {"resume": {"path": str(resume), "name": resume.name, "exists": resume.is_file()},
                "documents": documents}

    @app.get("/api/profile")
    def get_profile() -> dict[str, Any]:
        return profile_info()

    @app.post("/api/profile/resume")
    async def upload_resume(file: UploadFile) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in RESUME_SUFFIXES:
            raise HTTPException(422, "Upload your resume as .docx, .md or .txt.")
        target = paths.data_dir() / f"my_resume{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(await file.read())
        for other in RESUME_SUFFIXES - {suffix}:
            (paths.data_dir() / f"my_resume{other}").unlink(missing_ok=True)
        prefs = load_preferences()
        if prefs.get("resume_path"):  # a custom path would hide the upload; go back to the default location
            prefs["resume_path"] = ""
            save_preferences(prefs)
        return profile_info()

    @app.post("/api/profile/documents")
    async def upload_document(file: UploadFile) -> dict[str, Any]:
        name = Path(file.filename or "").name
        if Path(name).suffix.lower() not in PROFILE_SUFFIXES:
            raise HTTPException(422, "Profile documents must be .docx, .md or .txt.")
        if name.lower() == "answers.md":
            raise HTTPException(422, "answers.md is managed by the app; pick another file name.")
        folder = paths.profile_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(await file.read())
        return profile_info()

    @app.delete("/api/profile/documents/{name}")
    def delete_document(name: str) -> dict[str, Any]:
        target = paths.profile_dir() / Path(name).name
        if not target.is_file():
            raise HTTPException(404, "Document not found.")
        target.unlink()
        return profile_info()

    # --- status ----------------------------------------------------------------------------

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        prefs = load_preferences()
        env = load_env()
        runs = rt.db.list_runs(1)
        return {
            "resume": resume_path(prefs).is_file(),
            "auth_warning": auth_warning(),
            "keys": {"jsearch": bool(env.get("JSEARCH_API_KEY")),
                     "adzuna": bool(env.get("ADZUNA_APP_ID") and env.get("ADZUNA_APP_KEY"))},
            "libreoffice": _find_soffice() is not None,
            "quota": QuotaGuard(rt.db, budgets_from_prefs(prefs), rt.now).usage(),
            "search_running": rt.runner.running,
            "schedule_enabled": bool(prefs["schedule"]["enabled"]),
            "last_run": runs[0] if runs else None,
            "counts": rt.db.counts(now()),
        }

    # --- tailoring -------------------------------------------------------------------------

    @app.post("/api/jobs/{job_id}/tailor", status_code=202)
    async def start_tailor(job_id: int) -> dict[str, Any]:
        try:
            session = rt.tailor.start(job_id)
        except KeyError:
            raise HTTPException(404, "Job not found.") from None
        except MissingResume as exc:
            raise HTTPException(409, str(exc)) from None
        return session.to_dict()

    @app.get("/api/tailor/{session_id}")
    def get_tailor(session_id: str) -> dict[str, Any]:
        session = rt.tailor.sessions.get(session_id)
        if session is None:
            raise HTTPException(404, "Tailoring run not found.")
        return session.to_dict()

    @app.post("/api/tailor/{session_id}/answers")
    async def answer_tailor(session_id: str, body: AnswersBody) -> dict[str, Any]:
        try:
            rt.tailor.answer(session_id, [(a.question, a.answer) for a in body.answers])
        except KeyError:
            raise HTTPException(404, "Tailoring run not found.") from None
        except NotWaiting as exc:
            raise HTTPException(409, str(exc)) from None
        await asyncio.sleep(0)
        return rt.tailor.sessions[session_id].to_dict()

    @app.get("/api/files/{file_path:path}")
    def download(file_path: str) -> FileResponse:
        root = paths.output_dir().resolve()
        target = (root / file_path).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404, "File not found.")
        return FileResponse(target, filename=target.name)

    # --- UI ------------------------------------------------------------------------------

    if (STATIC_DIR / "index.html").is_file():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    else:

        @app.get("/")
        def no_ui() -> dict[str, str]:
            return {"message": "The UI isn't built yet. Run: cd frontend && npm install && npm run build"}

    return app
