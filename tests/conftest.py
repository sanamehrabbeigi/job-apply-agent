from pathlib import Path

import pytest
from docx import Document

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def sample_resume_docx(tmp_path: Path) -> Path:
    """A small resume built with Word styles, like a typical real resume."""
    doc = Document()
    doc.add_heading("Alex Rivera", level=1)
    doc.add_paragraph("Toronto, ON | alex.rivera@example.com")
    doc.add_heading("Experience", level=2)
    doc.add_heading("Data Analyst — Northwind Retail", level=3)
    doc.add_paragraph("Built 12 Tableau dashboards for merchandising.", style="List Bullet")
    doc.add_paragraph("Cut monthly reporting time from 3 days to 4 hours.", style="List Bullet")
    doc.add_heading("Skills", level=2)
    doc.add_paragraph("SQL, Python, Tableau")
    path = tmp_path / "resume.docx"
    doc.save(path)
    return path


@pytest.fixture
def sample_resume_md() -> str:
    return (EXAMPLES / "sample_resume.md").read_text(encoding="utf-8")


@pytest.fixture
def sample_job_text() -> str:
    return (EXAMPLES / "sample_job.txt").read_text(encoding="utf-8")
