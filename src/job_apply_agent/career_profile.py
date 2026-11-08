"""Your career profile: everything the agent may draw on besides your resume.

Put any number of documents in ``data/profile/`` (Word, Markdown or text): a full work
history, old resumes, project lists, performance reviews, certificates... The agent may
use any fact from them, choosing what fits each job.

Answers you give to the agent's questions are saved in ``data/profile/answers.md`` and
reused for every future job, so you only answer each question once. You can edit or
delete that file at any time.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .documents import read_resume

DEFAULT_PROFILE_DIR = Path("data/profile")
ANSWERS_FILE = "answers.md"
SUPPORTED = {".docx", ".md", ".markdown", ".txt"}


def load_profile(profile_dir: Path | None = DEFAULT_PROFILE_DIR, extra_files: list[Path] | None = None) -> str:
    """All profile documents as one Markdown text (the answers file is loaded separately)."""
    files: list[Path] = []
    if profile_dir and profile_dir.is_dir():
        files += sorted(
            p for p in profile_dir.iterdir()
            if p.suffix.lower() in SUPPORTED and p.name != ANSWERS_FILE and not p.name.startswith("~$")
        )
    for path in extra_files or []:
        if not path.is_file():
            raise FileNotFoundError(f"Profile document not found: {path}")
        if path not in files:
            files.append(path)
    sections = [f"### Document: {path.name}\n\n{read_resume(path).strip()}" for path in files]
    return "\n\n".join(sections)


def load_answers(profile_dir: Path | None = DEFAULT_PROFILE_DIR) -> str:
    if profile_dir is None:
        return ""
    path = profile_dir / ANSWERS_FILE
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def save_answers(profile_dir: Path, job_label: str, answers: list[tuple[str, str]]) -> Path:
    """Append question/answer pairs to the answers file and return its path."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    path = profile_dir / ANSWERS_FILE
    header = "" if path.exists() else (
        "# My answers to the agent's questions\n\n"
        "The agent treats these as facts about me and reuses them for every job.\n"
        "Edit or delete anything that is wrong.\n"
    )
    lines = [f"\n## {date.today():%Y-%m-%d} — asked while tailoring for: {job_label}\n"]
    for question, answer in answers:
        lines.append(f"- **Q:** {question}\n  **A:** {answer}")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(header + "\n".join(lines) + "\n")
    return path
