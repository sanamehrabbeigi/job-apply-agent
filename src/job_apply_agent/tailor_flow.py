"""The ask-then-rewrite tailoring loop, shared by the CLI and the web app.

Round 1 tailors the resume. If the match score is below the target and the agent has
questions, ``ask`` is called with them; true answers are saved to the profile and the
resume is rewritten, up to ``max_rounds`` rounds.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from . import tailor as tailor_module
from .career_profile import load_answers, load_profile, save_answers
from .documents import read_resume
from .outputs import save_outputs
from .tailor import DEFAULT_TARGET_SCORE, TailoredResume

AskFn = Callable[[list[str]], Awaitable[list[tuple[str, str]]]]
MessageFn = Callable[[str], None]


@dataclass
class TailorRequest:
    resume_path: Path
    job_text: str | None = None
    job_url: str | None = None
    profile_dir: Path | None = None
    extra_profile: list[Path] = field(default_factory=list)
    target_score: int = DEFAULT_TARGET_SCORE
    max_rounds: int = 3
    model: str | None = None
    instructions: str | None = None
    formats: list[str] = field(default_factory=lambda: ["md", "docx", "pdf"])
    out_dir: Path = field(default_factory=paths.output_dir)


@dataclass
class TailorOutcome:
    tailored: TailoredResume
    folder: Path
    files: list[Path]
    warnings: list[str]
    rounds: int


async def run_tailor_flow(
    req: TailorRequest,
    *,
    ask: AskFn | None = None,
    progress: MessageFn | None = None,
    status: MessageFn | None = None,
) -> TailorOutcome:
    """``progress`` gets the agent's own messages; ``status`` gets round-level updates."""
    say = status or (lambda _msg: None)
    resume_md = read_resume(req.resume_path)
    profile = load_profile(req.profile_dir, req.extra_profile)

    tailored: TailoredResume | None = None
    rounds = 0
    for round_no in range(1, max(1, req.max_rounds) + 1):
        rounds = round_no
        say(f"Round {round_no}: tailoring {req.resume_path.name} ... (usually a minute or two)")
        tailored = await tailor_module.tailor_resume(
            resume_md,
            job_text=req.job_text,
            job_url=req.job_url,
            profile=profile,
            answers=load_answers(req.profile_dir),
            target_score=req.target_score,
            extra_instructions=req.instructions,
            model=req.model,
            on_progress=progress,
        )
        say(f"Estimated match: {tailored.match_score}/100 (target {req.target_score})")
        if (
            tailored.match_score >= req.target_score
            or not tailored.questions_for_candidate
            or ask is None
            or req.profile_dir is None
            or round_no == req.max_rounds
        ):
            break
        answered = await ask(tailored.questions_for_candidate)
        if not answered:
            break
        path = save_answers(req.profile_dir, f"{tailored.job_title} at {tailored.company}", answered)
        say(f"Saved your answers to {path} (reused for future jobs).")

    assert tailored is not None
    reference = req.resume_path if req.resume_path.suffix.lower() == ".docx" else None
    folder, files, warnings = save_outputs(tailored, req.out_dir, req.formats, reference)
    return TailorOutcome(tailored=tailored, folder=folder, files=files, warnings=warnings, rounds=rounds)
