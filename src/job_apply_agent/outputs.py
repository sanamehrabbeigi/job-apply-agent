"""Write a tailored resume to disk as Markdown, Word and PDF, plus the report."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .documents import ConversionError, docx_to_pdf, write_docx
from .tailor import TailoredResume


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return slug[:max_len].strip("-") or "job"


def candidate_name(markdown: str) -> str:
    """Name from the resume's first '# ' heading, e.g. 'Jane_Doe'."""
    match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    return slugify(match.group(1), 40).replace("-", "_") if match else "Resume"


def save_outputs(
    tailored: TailoredResume, out_root: Path, formats: list[str], reference_docx: Path | None
) -> tuple[Path, list[Path], list[str]]:
    """Returns (folder, saved files, warnings). Markdown and the report are always saved."""
    folder_name = f"{date.today():%Y-%m-%d}_{slugify(tailored.company or 'company', 30)}_{slugify(tailored.job_title)}"
    folder = out_root / folder_name
    folder.mkdir(parents=True, exist_ok=True)

    base = f"{candidate_name(tailored.tailored_resume_markdown)}_Resume"
    if tailored.company:
        base += f"_{slugify(tailored.company, 30).replace('-', '_')}"

    saved: list[Path] = []
    warnings: list[str] = []
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
                warnings.append(f"PDF skipped: {exc}")
            if "docx" not in formats:
                docx_path.unlink(missing_ok=True)
    return folder, saved, warnings
