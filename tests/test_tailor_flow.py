from pathlib import Path

from test_profile_and_questions import SequenceQuery
from test_tailor import STRUCTURED

from job_apply_agent import outputs
from job_apply_agent.documents import ConversionError
from job_apply_agent.jobs import JobPosting
from job_apply_agent.tailor import TailoredResume
from job_apply_agent.tailor_flow import TailorRequest, run_tailor_flow


def test_job_posting_new_fields_default_and_to_text_unchanged():
    p = JobPosting(url="https://x/1", title="Data Analyst", company="Acme", description="Do analysis.")
    assert p.source == "" and p.external_id == "" and p.posted_at is None and p.remote is None
    assert p.description_is_partial is False and p.board == ""
    assert p.to_text().startswith("Source: https://x/1\nJob title: Data Analyst\nCompany: Acme")


async def test_flow_asks_saves_answers_and_rewrites(monkeypatch, tmp_path: Path, sample_resume_docx: Path):
    first = {**STRUCTURED, "match_score": 70, "questions_for_candidate": ["Used dbt?"]}
    second = {**STRUCTURED, "match_score": 88, "questions_for_candidate": []}
    fq = SequenceQuery([first, second])
    monkeypatch.setattr("job_apply_agent.tailor.query", fq)
    asked = []

    async def ask(questions):
        asked.append(questions)
        return [("Used dbt?", "Yes, 6 months at Northwind")]

    req = TailorRequest(resume_path=sample_resume_docx, job_text="Data Analyst at Maple", profile_dir=tmp_path / "p",
                        formats=["md"], out_dir=tmp_path / "out")
    outcome = await run_tailor_flow(req, ask=ask)

    assert asked == [["Used dbt?"]]
    assert outcome.rounds == 2 and outcome.tailored.match_score == 88
    assert "6 months at Northwind" in fq.prompts[1]
    assert (tmp_path / "p" / "answers.md").exists()
    assert {p.suffix for p in outcome.files} == {".md"}
    assert outcome.folder.parent == tmp_path / "out"


async def test_flow_without_ask_does_one_round(monkeypatch, tmp_path: Path, sample_resume_docx: Path):
    fq = SequenceQuery([{**STRUCTURED, "match_score": 60, "questions_for_candidate": ["Q?"]}])
    monkeypatch.setattr("job_apply_agent.tailor.query", fq)
    req = TailorRequest(resume_path=sample_resume_docx, job_text="job", profile_dir=tmp_path / "p",
                        formats=["md"], out_dir=tmp_path / "out")
    outcome = await run_tailor_flow(req, ask=None)
    assert outcome.rounds == 1 and len(fq.prompts) == 1


def test_save_outputs_reports_pdf_warning(monkeypatch, tmp_path: Path):
    def boom(_path):
        raise ConversionError("LibreOffice not found")

    monkeypatch.setattr(outputs, "docx_to_pdf", boom)
    tailored = TailoredResume.from_structured_output(STRUCTURED)
    folder, files, warnings = outputs.save_outputs(tailored, tmp_path, ["md", "docx", "pdf"], None)
    assert any("PDF skipped" in w for w in warnings)
    assert {p.suffix for p in files} == {".md", ".docx"}
    assert folder.name.endswith("_Maple-Commerce_Senior-Data-Analyst")
