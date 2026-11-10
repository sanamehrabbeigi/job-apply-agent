"""Claude match scoring for found jobs.

Uses Claude Haiku 5.5 by default: fast and light on subscription usage limits. Each job is
scored once per version of the candidate's documents (tracked by ``profile_hash``).
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

SCORE_SYSTEM_PROMPT = """You are a careful recruiter. You rate how well one candidate fits each job posting.

Rules:
- Judge only from the candidate's documents. Never assume skills or experience that are not shown.
- score is 0-100: 85+ strong fit (meets nearly all core requirements), 70-84 good fit with minor gaps,
  50-69 partial fit, below 50 weak fit.
- seniority_fit compares the level and years the job asks for with the candidate's:
  "under" = the job is more senior than the candidate, "over" = the job is more junior, "fit" = about right.
  A seniority mismatch is a gap: lower the score for it and say so; don't hide it.
- reasons: up to 3 short, specific reasons the candidate fits, citing their real experience.
- gaps: up to 3 short, specific requirements the candidate's documents don't show.
- summary: one plain sentence a busy person can scan.
- Return exactly one result per job, using each job's id exactly as given."""

SCORE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "summary": {"type": "string"},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                    "gaps": {"type": "array", "items": {"type": "string"}},
                    "seniority_fit": {"type": "string", "enum": ["under", "fit", "over"]},
                },
                "required": ["job_id", "score", "summary", "reasons", "gaps", "seniority_fit"],
            },
        }
    },
    "required": ["results"],
}

AUTH_FAILED = re.compile(r"authenticat|oauth|invalid api key|not logged in|login", re.I)
USAGE_LIMIT = re.compile(r"usage limit|rate[ _-]?limit|\b429\b|limit reached|overloaded|quota", re.I)
BOILERPLATE = re.compile(
    r"^\s*(?:#+\s*)?(?:benefits|perks|what we offer|why join us|equal (?:employment )?opportunity|eeo\b"
    r"|accommodation|accessibility|our commitment to diversity|diversity,? equity)",
    re.I | re.M,
)
MAX_DESCRIPTION_CHARS = 8000


class ScoringError(RuntimeError):
    pass


@dataclass
class JobScore:
    job_id: int
    score: int
    summary: str
    reasons: list[str]
    gaps: list[str]
    seniority_fit: str


@dataclass
class ScoreOutcome:
    scores: list[JobScore] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    usage_limited: bool = False
    auth_failed: bool = False


def profile_hash(resume: str, profile: str) -> str:
    """Identifies the version of the candidate's documents a score was made from.

    Saved answers are left out on purpose: they grow every time she answers a tailoring question,
    and re-scoring every job for each answer would waste usage. They are still sent when scoring."""
    return hashlib.sha256("\x1e".join((resume, profile)).encode("utf-8")).hexdigest()[:16]


def trim_description(text: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    """Drop benefits/EEO boilerplate near the end (never the start), then cap the length."""
    text = (text or "").strip()
    for match in BOILERPLATE.finditer(text):
        if match.start() > len(text) * 0.4:
            text = text[: match.start()].rstrip()
            break
    if len(text) > limit:
        text = text[:limit].rstrip() + " …"
    return text


def build_prompt(jobs: list[dict[str, Any]], *, resume: str, profile: str, answers: str) -> str:
    parts = [f"<candidate_resume>\n{resume.strip()}\n</candidate_resume>"]
    if profile.strip():
        parts.append(f"<candidate_profile>\n{profile.strip()}\n</candidate_profile>")
    if answers.strip():
        parts.append(f"<candidate_answers>\n{answers.strip()}\n</candidate_answers>")
    parts.append("Rate the candidate against each job below.")
    for job in jobs:
        parts.append(
            f'<job id="{job["id"]}">\nTitle: {job["title"]}\nCompany: {job["company"]}\n'
            f'Location: {job["location"] or "not stated"}\n\n{trim_description(job["description"]) or "(no description)"}\n</job>'
        )
    return "\n\n".join(parts)


def build_options(model: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SCORE_SYSTEM_PROMPT,
        tools=[],
        allowed_tools=[],
        permission_mode="dontAsk",
        setting_sources=[],
        output_format={"type": "json_schema", "schema": SCORE_OUTPUT_SCHEMA},
        max_turns=3,
        model=model,
    )


async def _score_batch(jobs, *, resume, profile, answers, model, query_fn) -> list[JobScore]:
    result: ResultMessage | None = None
    async for message in query_fn(prompt=build_prompt(jobs, resume=resume, profile=profile, answers=answers),
                                  options=build_options(model)):
        if isinstance(message, ResultMessage):
            result = message
    if result is None:
        raise ScoringError("Claude finished without a result.")
    if result.is_error or result.subtype != "success":
        raise ScoringError("; ".join(result.errors or []) or result.result or result.stop_reason or result.subtype)
    data = result.structured_output
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ScoringError("Claude did not return scores in the expected format.")
    wanted = {job["id"] for job in jobs}
    scores = []
    for item in data["results"]:
        try:
            job_id = int(item["job_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if job_id not in wanted:
            continue
        wanted.discard(job_id)
        scores.append(JobScore(
            job_id=job_id,
            score=max(0, min(100, int(item.get("score", 0)))),
            summary=str(item.get("summary", "")).strip(),
            reasons=[str(r) for r in item.get("reasons", [])][:3],
            gaps=[str(g) for g in item.get("gaps", [])][:3],
            seniority_fit=item.get("seniority_fit") if item.get("seniority_fit") in ("under", "fit", "over") else "fit",
        ))
    return scores


async def score_jobs(
    jobs: list[dict[str, Any]],
    *,
    resume: str,
    profile: str,
    answers: str,
    model: str,
    batch_size: int = 5,
    concurrency: int = 2,
    on_progress: Callable[[int, int], None] | None = None,
    query_fn=None,
) -> ScoreOutcome:
    query_fn = query_fn or query
    outcome = ScoreOutcome()
    batches = [jobs[i: i + max(1, batch_size)] for i in range(0, len(jobs), max(1, batch_size))]
    semaphore = asyncio.Semaphore(max(1, concurrency))
    stop = asyncio.Event()
    done = 0

    async def run(batch: list[dict[str, Any]]) -> None:
        nonlocal done
        ids = [job["id"] for job in batch]
        async with semaphore:
            if stop.is_set():
                outcome.failed.extend(ids)
                return
            try:
                scores = await _score_batch(batch, resume=resume, profile=profile, answers=answers, model=model,
                                            query_fn=query_fn)
            except Exception as exc:  # noqa: BLE001 - any failure leaves the batch unscored for next time
                message = str(exc) or exc.__class__.__name__
                outcome.errors.append(message)
                outcome.failed.extend(ids)
                if AUTH_FAILED.search(message):
                    outcome.auth_failed = True
                    stop.set()
                elif USAGE_LIMIT.search(message):
                    outcome.usage_limited = True
                    stop.set()
                return
        outcome.scores.extend(scores)
        returned = {s.job_id for s in scores}
        outcome.failed.extend(i for i in ids if i not in returned)
        done += len(batch)
        if on_progress:
            on_progress(done, len(jobs))

    await asyncio.gather(*(run(batch) for batch in batches))
    return outcome
