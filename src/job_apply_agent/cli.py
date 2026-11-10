"""Command-line interface: ``job-agent tailor|fetch-job|render|search|serve ...``."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from pathlib import Path

from . import __version__, paths
from .documents import ConversionError, docx_to_pdf, write_docx
from .envfile import export_claude_token
from .jobs import JobFetchError, fetch_job
from .outputs import candidate_name, save_outputs, slugify  # noqa: F401  (re-exported for compatibility)
from .preferences import load_preferences, resume_path
from .tailor import DEFAULT_TARGET_SCORE, TailoringError, auth_warning
from .tailor_flow import TailorRequest, run_tailor_flow

FORMATS = ("md", "docx", "pdf")


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
    t.add_argument("--resume", type=Path, help="Your master resume (.docx, .md or .txt). Default: the one set in the app.")
    job = t.add_mutually_exclusive_group(required=True)
    job.add_argument("--job-url", help="Link to the job posting (LinkedIn links of any kind work).")
    job.add_argument("--job-file", type=Path, help="Text file with the job posting.")
    job.add_argument("--job-text", help="The job posting text itself.")
    t.add_argument(
        "--profile-dir",
        type=Path,
        default=paths.profile_dir(),
        help=f"Folder with your career profile documents and saved answers (default: {paths.profile_dir()}).",
    )
    t.add_argument("--profile", type=Path, action="append", default=[], help="Extra profile document (repeatable).")
    t.add_argument(
        "--target-score", type=int, default=DEFAULT_TARGET_SCORE, help="Match score to aim for (default: 85)."
    )
    t.add_argument("--max-rounds", type=int, default=3, help="Max rewrite rounds with your answers (default: 3).")
    t.add_argument("--no-questions", action="store_true", help="Don't ask questions; do a single rewrite.")
    t.add_argument("--jobs-dir", type=Path, default=paths.jobs_dir(), help="Where fetched postings are saved.")
    t.add_argument("--out", type=Path, default=paths.output_dir(), help="Output folder (default: ./output).")
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
    f.add_argument("--jobs-dir", type=Path, default=paths.jobs_dir(), help="Folder to save into (default: data/jobs).")

    r = sub.add_parser("render", help="Re-create the .docx/.pdf from a (hand-edited) resume .md file.")
    r.add_argument("markdown", type=Path, help="Resume Markdown file, e.g. output/.../Name_Resume_Company.md")
    r.add_argument("--formats", type=parse_formats, default=["docx", "pdf"], help="docx,pdf (default: both)")
    r.add_argument("--reference", type=Path, help="Your original .docx resume (page margins are copied).")
    se = sub.add_parser("search", help="Search all job sources once and score new jobs (no web UI needed).")
    se.add_argument(
        "--sources",
        type=lambda v: [s.strip() for s in v.split(",") if s.strip()],
        help="Comma-separated sources, e.g. greenhouse,lever (default: all enabled).",
    )
    se.add_argument("--no-score", action="store_true", help="Collect jobs without Claude scoring.")
    sv = sub.add_parser("serve", help="Open the job app in your browser (http://127.0.0.1:8000).")
    sv.add_argument("--port", type=int, default=8000, help="Port (default: 8000).")
    sv.add_argument("--no-browser", action="store_true", help="Don't open the browser automatically.")
    sv.add_argument("--no-schedule", action="store_true", help="Don't run scheduled searches while the app is open.")
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

    resume = args.resume or resume_path(load_preferences())
    if not resume.is_file():
        raise FileNotFoundError(f"Resume not found: {resume}. Pass --resume or add it in the app's Settings.")
    job_text, job_url = resolve_job(args)
    interactive = not args.no_questions and (ask is not input or sys.stdin.isatty())

    async def terminal_ask(questions: list[str]) -> list[tuple[str, str]]:
        return ask_questions(questions, ask)

    req = TailorRequest(
        resume_path=resume,
        job_text=job_text,
        job_url=job_url,
        profile_dir=args.profile_dir,
        extra_profile=args.profile,
        target_score=args.target_score,
        max_rounds=args.max_rounds,
        model=args.model,
        instructions=args.instructions,
        formats=args.formats,
        out_dir=args.out,
    )
    outcome = await run_tailor_flow(
        req,
        ask=terminal_ask if interactive else None,
        progress=None if args.quiet else (lambda msg: print(f"  · {msg}")),
        status=lambda msg: print(f"\n{msg}" if msg.startswith("Round") else msg),
    )
    for note in outcome.warnings:
        print(f"! {note}", file=sys.stderr)

    tailored = outcome.tailored
    print(f"\nDone: {tailored.job_title}{' at ' + tailored.company if tailored.company else ''}")
    print(f"Estimated match: {tailored.match_score}/100")
    if tailored.match_score < args.target_score:
        print("Below target. See the report's questions; answering them truthfully is the way to raise it.")
    if tailored.missing_keywords:
        print("Not shown in your resume or profile (not added): " + ", ".join(tailored.missing_keywords))
    print(f"\nSaved to {outcome.folder}/")
    for path in outcome.files:
        print(f"  - {path.name}")
    print("\nReview the resume before sending it: check every line is true and reads like you.")
    return 0

def format_stat(name: str, stat: dict) -> str:
    status = stat.get("status")
    if status == "skipped" and name != "scoring":
        return f"{name}: skipped ({stat.get('reason')})"
    if status == "error":
        return f"{name}: error: {stat.get('error')}"
    if name == "scoring":
        return f"scoring: {stat.get('message', '')}"
    line = f"{name}: {stat.get('fetched', 0)} fetched, {stat.get('relevant', 0)} relevant, {stat.get('new', 0)} new"
    if stat.get("warnings"):
        line += f" ({len(stat['warnings'])} warning(s), first: {stat['warnings'][0]})"
    return line


def run_search(args: argparse.Namespace) -> int:
    from . import runtime

    rt = runtime.build_runtime()
    run_id = asyncio.run(rt.runner.run(trigger="cli", sources=args.sources, score=not args.no_score))
    run = rt.db.get_run(run_id)
    for name, stat in run["sources"].items():
        print(format_stat(name, stat))
    if run["error"]:
        print(f"Error: {run['error']}", file=sys.stderr)
        return 1
    print("Open the app to see the ranked list: job-agent serve")
    return 0


def run_serve(args: argparse.Namespace) -> int:
    import threading
    import webbrowser

    import uvicorn

    from .web import app as web_app

    application = web_app.create_app(start_scheduler=not args.no_schedule)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Job app running at {url} (press Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(application, host="127.0.0.1", port=args.port, log_level="info")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    export_claude_token()
    try:
        if args.command == "tailor":
            return asyncio.run(run_tailor(args))
        if args.command == "render":
            return run_render(args)
        if args.command == "fetch-job":
            return run_fetch_job(args)
        if args.command == "search":
            return run_search(args)
        if args.command == "serve":
            return run_serve(args)
    except (FileNotFoundError, ConversionError, TailoringError, JobFetchError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
