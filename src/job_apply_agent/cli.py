"""Command-line interface: ``job-agent tailor ...``, ``job-agent fetch-job ...``, ``job-agent render ...``."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

from . import __version__
from .career_profile import DEFAULT_PROFILE_DIR, load_answers, load_profile, save_answers
from .documents import ConversionError, docx_to_pdf, read_resume, write_docx
from .jobs import JobFetchError, fetch_job
from .tailor import DEFAULT_TARGET_SCORE, TailoredResume, TailoringError, auth_warning, tailor_resume

FORMATS = ("md", "docx", "pdf")


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return slug[:max_len].strip("-") or "job"


def candidate_name(markdown: str) -> str:
    """Name from the resume's first '# ' heading, e.g. 'Jane_Doe'."""
    match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    return slugify(match.group(1), 40).replace("-", "_") if match else "Resume"


def parse_formats(value: str) -> list[str]:
    formats = [f.strip().lower() for f in value.split(",") if f.strip()]
    bad = [f for f in formats if f not in FORMATS]
    if bad:
        raise argparse.ArgumentTypeError(f"Unknown format(s): {', '.join(bad)}. Choose from {', '.join(FORMATS)}.")
    return formats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="job-agent", description="Your personal job-application agent.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    t = sub.add_parser("tailor", help="Tailor your resume to a job posting.")
    t.add_argument("--resume", required=True, type=Path, help="Your master resume (.docx, .md or .txt).")
    job = t.add_mutually_exclusive_group(required=True)
    job.add_argument("--job-url", help="Link to the job posting (LinkedIn links of any kind work).")
    job.add_argument("--job-file", type=Path, help="Text file with the job posting.")
    job.add_argument("--job-text", help="The job posting text itself.")
    t.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help=f"Folder with your career profile documents and saved answers (default: {DEFAULT_PROFILE_DIR}).",
    )
    t.add_argument("--profile", type=Path, action="append", default=[], help="Extra profile document (repeatable).")
    t.add_argument(
        "--target-score", type=int, default=DEFAULT_TARGET_SCORE, help="Match score to aim for (default: 85)."
    )
    t.add_argument("--max-rounds", type=int, default=3, help="Max rewrite rounds with your answers (default: 3).")
    t.add_argument("--no-questions", action="store_true", help="Don't ask questions; do a single rewrite.")
    t.add_argument("--jobs-dir", type=Path, default=Path("data/jobs"), help="Where fetched postings are saved.")
    t.add_argument("--out", type=Path, default=Path("output"), help="Output folder (default: ./output).")
    t.add_argument(
        "--formats",
        type=parse_formats,
        default=["md", "docx", "pdf"],
        help="Comma-separated output formats: md,docx,pdf (default: all). Markdown is always saved.",
    )
    t.add_argument("--model", help="Claude model alias or ID (default: your account's default).")
    t.add_argument("--instructions", help="Extra instructions, e.g. 'Keep it to one page.'")
    t.add_argument("--quiet", action="store_true", help="Don't print agent progress.")

    f = sub.add_parser("fetch-job", help="Save a job posting from a link as a text file.")
    f.add_argument("url", help="Job posting link (LinkedIn links of any kind work).")
    f.add_argument("--jobs-dir", type=Path, default=Path("data/jobs"), help="Folder to save into (default: data/jobs).")

    r = sub.add_parser("render", help="Re-create the .docx/.pdf from a (hand-edited) resume .md file.")
    r.add_argument("markdown", type=Path, help="Resume Markdown file, e.g. output/.../Name_Resume_Company.md")
    r.add_argument("--formats", type=parse_formats, default=["docx", "pdf"], help="docx,pdf (default: both)")
    r.add_argument("--reference", type=Path, help="Your original .docx resume (page margins are copied).")
    return parser


def run_render(args: argparse.Namespace) -> int:
    if not args.markdown.is_file():
        raise FileNotFoundError(f"Markdown file not found: {args.markdown}")
    docx_path = write_docx(args.markdown.read_text(encoding="utf-8"), args.markdown.with_suffix(".docx"), args.reference)
    saved = [docx_path] if "docx" in args.formats else []
    if "pdf" in args.formats:
        saved.append(docx_to_pdf(docx_path))
        if "docx" not in args.formats:
            docx_path.unlink(missing_ok=True)
    for path in saved:
        print(f"Saved {path}")
    return 0


def save_outputs(
    tailored: TailoredResume, out_root: Path, formats: list[str], reference_docx: Path | None
) -> tuple[Path, list[Path]]:
    folder_name = f"{date.today():%Y-%m-%d}_{slugify(tailored.company or 'company', 30)}_{slugify(tailored.job_title)}"
    folder = out_root / folder_name
    folder.mkdir(parents=True, exist_ok=True)

    base = f"{candidate_name(tailored.tailored_resume_markdown)}_Resume"
    if tailored.company:
        base += f"_{slugify(tailored.company, 30).replace('-', '_')}"

    saved: list[Path] = []
    md_path = folder / f"{base}.md"
    md_path.write_text(tailored.tailored_resume_markdown + "\n", encoding="utf-8")
    saved.append(md_path)

    report_path = folder / "tailoring_report.md"
    report_path.write_text(tailored.report_markdown(), encoding="utf-8")
    saved.append(report_path)

    if "docx" in formats or "pdf" in formats:
        docx_path = write_docx(tailored.tailored_resume_markdown, folder / f"{base}.docx", reference_docx)
        if "docx" in formats:
            saved.append(docx_path)
        if "pdf" in formats:
            try:
                saved.append(docx_to_pdf(docx_path))
            except ConversionError as exc:
                print(f"! PDF skipped: {exc}", file=sys.stderr)
            if "docx" not in formats:
                docx_path.unlink(missing_ok=True)
    return folder, saved


def run_fetch_job(args: argparse.Namespace) -> int:
    posting = fetch_job(args.url)
    path = posting.save(args.jobs_dir)
    print(f"Saved {posting.title or 'job posting'}{' at ' + posting.company if posting.company else ''} to {path}")
    return 0


def resolve_job(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Return (job_text, job_url_for_agent). Links are fetched here; the agent's WebFetch is the fallback."""
    if args.job_text:
        return args.job_text, None
    if args.job_file:
        return args.job_file.read_text(encoding="utf-8"), None
    try:
        posting = fetch_job(args.job_url)
    except JobFetchError as exc:
        print(f"! {exc}\n  Letting the agent try to read the page instead.", file=sys.stderr)
        return None, args.job_url
    path = posting.save(args.jobs_dir)
    print(f"Job: {posting.title}{' at ' + posting.company if posting.company else ''} (saved to {path})")
    return posting.to_text(), None


def ask_questions(questions: list[str], ask: Callable[[str], str] = input) -> list[tuple[str, str]]:
    """Ask each question in the terminal; empty answers are skipped."""
    print("\nAnswer truthfully to raise the match. Press Enter to skip a question.")
    answered = []
    for i, question in enumerate(questions, 1):
        print(f"\n{i}. {question}")
        answer = ask("   > ").strip()
        if answer:
            answered.append((question, answer))
    return answered


async def run_tailor(args: argparse.Namespace, ask: Callable[[str], str] = input) -> int:
    warning = auth_warning()
    if warning:
        print(f"! {warning}", file=sys.stderr)

    resume_md = read_resume(args.resume)
    profile = load_profile(args.profile_dir, args.profile)
    if profile:
        print(f"Using career profile from {args.profile_dir}" + (f" and {len(args.profile)} extra file(s)" if args.profile else ""))
    job_text, job_url = resolve_job(args)
    interactive = not args.no_questions and (ask is not input or sys.stdin.isatty())
    progress = None if args.quiet else (lambda msg: print(f"  · {msg}"))

    tailored: TailoredResume | None = None
    for round_no in range(1, max(1, args.max_rounds) + 1):
        print(f"\nRound {round_no}: tailoring {args.resume.name} ... (usually a minute or two)")
        tailored = await tailor_resume(
            resume_md,
            job_text=job_text,
            job_url=job_url,
            profile=profile,
            answers=load_answers(args.profile_dir),
            target_score=args.target_score,
            extra_instructions=args.instructions,
            model=args.model,
            on_progress=progress,
        )
        print(f"Estimated match: {tailored.match_score}/100 (target {args.target_score})")
        if (
            tailored.match_score >= args.target_score
            or not tailored.questions_for_candidate
            or not interactive
            or round_no == args.max_rounds
        ):
            break
        answered = ask_questions(tailored.questions_for_candidate, ask)
        if not answered:
            break
        path = save_answers(args.profile_dir, f"{tailored.job_title} at {tailored.company}", answered)
        print(f"Saved your answers to {path} (reused for future jobs).")

    assert tailored is not None
    reference = args.resume if args.resume.suffix.lower() == ".docx" else None
    folder, saved = save_outputs(tailored, args.out, args.formats, reference)

    print(f"\nDone: {tailored.job_title}{' at ' + tailored.company if tailored.company else ''}")
    print(f"Estimated match: {tailored.match_score}/100")
    if tailored.match_score < args.target_score:
        print("Below target. See the report's questions; answering them truthfully is the way to raise it.")
    if tailored.missing_keywords:
        print("Not shown in your resume or profile (not added): " + ", ".join(tailored.missing_keywords))
    print(f"\nSaved to {folder}/")
    for path in saved:
        print(f"  - {path.name}")
    print("\nReview the resume before sending it: check every line is true and reads like you.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "tailor":
            return asyncio.run(run_tailor(args))
        if args.command == "render":
            return run_render(args)
        if args.command == "fetch-job":
            return run_fetch_job(args)
    except (FileNotFoundError, ConversionError, TailoringError, JobFetchError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
