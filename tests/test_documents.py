from pathlib import Path

import pytest
from docx import Document

from job_apply_agent.documents import ConversionError, _find_soffice, docx_to_pdf, read_resume, write_docx


def test_read_docx_resume_as_markdown(sample_resume_docx: Path):
    md = read_resume(sample_resume_docx)
    assert md.startswith("# Alex Rivera")
    assert "## Experience" in md
    assert "Built 12 Tableau dashboards" in md
    assert "- Cut monthly reporting time" in md


def test_read_markdown_resume(tmp_path: Path):
    path = tmp_path / "r.md"
    path.write_text("# Jane\n\n- bullet\n", encoding="utf-8")
    assert read_resume(path) == "# Jane\n\n- bullet\n"


def test_read_resume_errors(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_resume(tmp_path / "missing.docx")
    bad = tmp_path / "resume.rtf"
    bad.write_text("x")
    with pytest.raises(ConversionError):
        read_resume(bad)


def test_write_docx_uses_reference_styles(tmp_path: Path, sample_resume_docx: Path, sample_resume_md: str):
    # Give the reference resume a distinctive body font; the output should inherit it.
    ref = Document(sample_resume_docx)
    ref.styles["Normal"].font.name = "Georgia"
    ref.save(sample_resume_docx)

    out = write_docx(sample_resume_md, tmp_path / "out" / "tailored.docx", reference_docx=sample_resume_docx)
    doc = Document(out)
    texts = [p.text for p in doc.paragraphs]
    assert "Alex Rivera" in texts
    assert any("Tableau dashboards" in t for t in texts)
    assert doc.styles["Normal"].font.name == "Georgia"


@pytest.mark.skipif(_find_soffice() is None, reason="LibreOffice not installed")
def test_docx_to_pdf(tmp_path: Path, sample_resume_md: str):
    docx = write_docx(sample_resume_md, tmp_path / "r.docx")
    pdf = docx_to_pdf(docx)
    assert pdf.exists()
    assert pdf.read_bytes().startswith(b"%PDF")
