from pathlib import Path

import pytest
from docx import Document
from docx.shared import Inches

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


def test_write_docx_renders_resume_layout(tmp_path: Path, sample_resume_docx: Path, sample_resume_md: str):
    # The output takes its page margins from the user's own resume.
    ref = Document(sample_resume_docx)
    ref.sections[0].left_margin = Inches(0.6)
    ref.save(sample_resume_docx)

    out = write_docx(sample_resume_md, tmp_path / "out" / "tailored.docx", reference_docx=sample_resume_docx)
    doc = Document(out)
    paras = doc.paragraphs
    texts = [p.text for p in paras]

    assert texts[0] == "ALEX RIVERA"  # centered, uppercase name
    assert "alex.rivera@example.com" in "".join(r.text for r in paras[1]._p.iter() if hasattr(r, "text") and r.text)
    assert "EXPERIENCE" in texts
    assert "Data Analyst\tJan 2023 – Present" in texts  # dates after a right-aligned tab
    assert "Northwind Retail | Toronto, ON" in texts
    bullets = [p for p in paras if p.style.name == "List Bullet"]
    assert any("Tableau dashboards" in p.text for p in bullets)
    assert round(doc.sections[0].left_margin.inches, 2) == 0.6


@pytest.mark.skipif(_find_soffice() is None, reason="LibreOffice not installed")
def test_docx_to_pdf(tmp_path: Path, sample_resume_md: str):
    docx = write_docx(sample_resume_md, tmp_path / "r.docx")
    pdf = docx_to_pdf(docx)
    assert pdf.exists()
    assert pdf.read_bytes().startswith(b"%PDF")


def test_read_resume_from_text_pdf(tmp_path):
    from pdf_helpers import write_text_pdf

    from job_apply_agent.documents import read_resume

    pdf = write_text_pdf(tmp_path / "cv.pdf", ["Alex Rivera", "Data Analyst (Northwind Retail)", "SQL, Python, Tableau"])
    text = read_resume(pdf)
    assert "Alex Rivera" in text and "Data Analyst (Northwind Retail)" in text and "Tableau" in text


def test_read_resume_rejects_scanned_pdf(tmp_path):
    import pytest
    from pdf_helpers import write_blank_pdf

    from job_apply_agent.documents import ConversionError, read_resume

    with pytest.raises(ConversionError, match="no selectable text"):
        read_resume(write_blank_pdf(tmp_path / "scan.pdf"))
