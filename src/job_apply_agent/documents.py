"""Reading and writing resume documents.

- DOCX -> Markdown with pandoc (bundled via ``pypandoc-binary``), so Claude reads clean text.
- Markdown -> DOCX with our own renderer (``render.py``): a clean, classic single-column
  layout; page margins are taken from your original resume.
- DOCX -> PDF with LibreOffice (``soffice``) if installed, otherwise Microsoft Word
  through the optional ``docx2pdf`` package.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pypandoc

from .render import render_resume_docx


class ConversionError(RuntimeError):
    """Raised when a document cannot be converted."""


def read_resume(path: str | Path) -> str:
    """Return the resume at ``path`` as Markdown text.

    Supports .docx (converted with pandoc) and .md/.txt (read as-is).
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Resume not found: {path}")

    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".docx":
        # gfm keeps headings, bullet lists and bold text; --wrap=none keeps one bullet per line.
        return pypandoc.convert_file(str(path), "gfm", extra_args=["--wrap=none"]).strip()
    raise ConversionError(f"Unsupported resume format '{suffix}'. Use .docx, .md or .txt.")


def write_docx(markdown: str, out_path: str | Path, reference_docx: str | Path | None = None) -> Path:
    """Write ``markdown`` (resume dialect, see render.py) to a styled .docx file."""
    return render_resume_docx(markdown, out_path, reference_docx=reference_docx)


def docx_to_pdf(docx_path: str | Path, pdf_path: str | Path | None = None) -> Path:
    """Convert a .docx file to PDF. Tries LibreOffice first, then Microsoft Word (docx2pdf)."""
    docx_path = Path(docx_path).resolve()
    pdf_path = Path(pdf_path).resolve() if pdf_path else docx_path.with_suffix(".pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    soffice = _find_soffice()
    if soffice:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(docx_path)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            produced = Path(tmp) / (docx_path.stem + ".pdf")
            if result.returncode != 0 or not produced.exists():
                raise ConversionError(f"LibreOffice could not convert to PDF:\n{result.stderr or result.stdout}")
            shutil.move(str(produced), pdf_path)
        return pdf_path

    try:
        from docx2pdf import convert  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConversionError(
            "No PDF converter found. Install LibreOffice (https://www.libreoffice.org/), "
            "or on Windows/macOS with Microsoft Word run: pip install 'job-apply-agent[word]'"
        ) from exc
    convert(str(docx_path), str(pdf_path))
    return pdf_path


def _find_soffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return None
