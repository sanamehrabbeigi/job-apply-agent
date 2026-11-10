from pathlib import Path

from docx import Document
from test_tailor import STRUCTURED, make_result

from job_apply_agent import cli, jobs
from job_apply_agent.career_profile import load_answers, load_profile, save_answers


def test_load_profile_reads_folder_and_extra_files(tmp_path: Path):
    folder = tmp_path / "profile"
    folder.mkdir()
    doc = Document()
    doc.add_paragraph("Led a churn analysis for 40 clients.")
    doc.save(folder / "work_history.docx")
    (folder / "skills.md").write_text("Looker, Google Sheets", encoding="utf-8")
    (folder / "answers.md").write_text("# answers", encoding="utf-8")  # loaded separately
    (folder / "~$lock.docx").write_text("x")  # Word lock file: ignored
    extra = tmp_path / "projects.txt"
    extra.write_text("Built a forecasting model.", encoding="utf-8")

    profile = load_profile(folder, [extra])
    assert "### Document: skills.md" in profile and "### Document: work_history.docx" in profile
    assert "churn analysis" in profile and "forecasting model" in profile
    assert "# answers" not in profile


def test_save_and_load_answers(tmp_path: Path):
    save_answers(tmp_path, "Data Analyst at Acme", [("Have you used Looker?", "Yes, at Ivey for 3 months")])
    save_answers(tmp_path, "BI Analyst at Beta", [("B.Sc. degree?", "Yes")])
    answers = load_answers(tmp_path)
    assert answers.count("**Q:**") == 2
    assert "Yes, at Ivey for 3 months" in answers and "Data Analyst at Acme" in answers


class SequenceQuery:
    """Fake SDK query that returns one structured result per call."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def __call__(self, *, prompt, options):
        self.prompts.append(prompt)
        output = self.outputs.pop(0)

        async def gen():
            yield make_result(structured_output=output)

        return gen()


def test_question_loop_saves_answers_and_rewrites(monkeypatch, tmp_path: Path, sample_resume_docx: Path):
    first = {**STRUCTURED, "match_score": 72, "questions_for_candidate": ["Have you used Looker?", "Any B2B SaaS?"]}
    second = {**STRUCTURED, "match_score": 87, "questions_for_candidate": []}
    fq = SequenceQuery([first, second])
    monkeypatch.setattr("job_apply_agent.tailor.query", fq)
    replies = iter(["Yes, Looker at Ivey for a class project", ""])  # second question skipped
    profile_dir = tmp_path / "profile"

    args = cli.build_parser().parse_args(
        ["tailor", "--resume", str(sample_resume_docx), "--job-text", "Data Analyst at Maple", "--quiet",
         "--profile-dir", str(profile_dir), "--out", str(tmp_path / "out"), "--formats", "md"]
    )
    import asyncio

    assert asyncio.run(cli.run_tailor(args, ask=lambda _prompt: next(replies))) == 0

    assert len(fq.prompts) == 2
    assert "<candidate_answers>" not in fq.prompts[0]
    assert "Looker at Ivey" in fq.prompts[1] and "Any B2B SaaS?" not in fq.prompts[1]
    assert "Target match score: 85/100" in fq.prompts[0]
    assert "Looker at Ivey" in (profile_dir / "answers.md").read_text()
    report = next((tmp_path / "out").glob("*/tailoring_report.md")).read_text()
    assert "87/100" in report


def test_question_loop_stops_at_target(monkeypatch, tmp_path: Path, sample_resume_docx: Path):
    fq = SequenceQuery([{**STRUCTURED, "match_score": 90}])
    monkeypatch.setattr("job_apply_agent.tailor.query", fq)
    args = cli.build_parser().parse_args(
        ["tailor", "--resume", str(sample_resume_docx), "--job-text", "job", "--quiet",
         "--profile-dir", str(tmp_path / "p"), "--out", str(tmp_path / "out"), "--formats", "md"]
    )
    import asyncio

    asyncio.run(cli.run_tailor(args, ask=lambda _p: (_ for _ in ()).throw(AssertionError("should not ask"))))
    assert len(fq.prompts) == 1


def test_tailor_with_job_url_fetches_posting_first(monkeypatch, tmp_path: Path, sample_resume_docx: Path):
    from test_jobs import LINKEDIN_PAGE

    monkeypatch.setattr(jobs, "_http_get", lambda url, timeout: LINKEDIN_PAGE)
    fq = SequenceQuery([{**STRUCTURED, "match_score": 90}])
    monkeypatch.setattr("job_apply_agent.tailor.query", fq)
    code = cli.main(
        ["tailor", "--resume", str(sample_resume_docx), "--job-url", "https://www.linkedin.com/jobs/view/123456789/",
         "--quiet", "--profile-dir", str(tmp_path / "p"), "--jobs-dir", str(tmp_path / "jobs"),
         "--out", str(tmp_path / "out"), "--formats", "md"]
    )
    assert code == 0
    assert "<job_posting>" in fq.prompts[0] and "Example Co" in fq.prompts[0]  # text, not WebFetch
    assert (tmp_path / "jobs" / "example-co_data-analyst_123456789.txt").exists()
