"""Command-line interface: ``job-agent tailor ...``."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .documents import ConversionError, docx_to_pdf, read_resume, write_docx
from .tailor import TailoredResume, TailoringError, auth_warning, tailor_resume

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
    job.add_argument("--job-file", type=Path, help="Text file with the job posting (most reliable).")
    job.add_argument("--job-url", help="URL of the job posting (some sites, e.g. LinkedIn, block fetching).")
    job.add_argument("--job-text", help="The job posting text itself.")
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
    return parser


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


async def run_tailor(args: argparse.Namespace) -> int:
    warning = auth_warning()
    if warning:
        print(f"! {warning}", file=sys.stderr)

    resume_md = read_resume(args.resume)
    job_text = args.job_text or (args.job_file.read_text(encoding="utf-8") if args.job_file else None)

    print(f"Tailoring {args.resume.name} ... (this usually takes a minute or two)")
    tailored = await tailor_resume(
        resume_md,
        job_text=job_text,
        job_url=args.job_url,
        extra_instructions=args.instructions,
        model=args.model,
        on_progress=None if args.quiet else (lambda msg: print(f"  · {msg}")),
    )

    reference = args.resume if args.resume.suffix.lower() == ".docx" else None
    folder, saved = save_outputs(tailored, args.out, args.formats, reference)

    print(f"\nDone: {tailored.job_title}{' at ' + tailored.company if tailored.company else ''}")
    print(f"Estimated match: {tailored.match_score}/100")
    if tailored.missing_keywords:
        print("Not shown in your resume (not added): " + ", ".join(tailored.missing_keywords))
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
    except (FileNotFoundError, ConversionError, TailoringError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
