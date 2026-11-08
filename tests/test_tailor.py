from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from job_apply_agent import cli, tailor
from job_apply_agent.documents import _find_soffice
from job_apply_agent.tailor import TailoringError, auth_warning, build_prompt, tailor_resume

STRUCTURED = {
    "job_title": "Senior Data Analyst",
    "company": "Maple Commerce",
    "tailored_resume_markdown": "# Alex Rivera\n\nToronto | alex@example.com\n\n## Summary\n\nAnalyst.\n",
    "match_score": 82,
    "matched_keywords": ["SQL", "A/B testing"],
    "missing_keywords": ["dbt", "Snowflake"],
    "changes": ["Rewrote summary for pricing focus"],
    "questions_for_candidate": ["Have you used dbt?"],
    "notes": "",
}


def make_result(**overrides) -> ResultMessage:
    fields = dict(
        subtype="success",
        duration_ms=1000,
        duration_api_ms=900,
        is_error=False,
        num_turns=1,
        session_id="test",
        result="done",
        structured_output=STRUCTURED,
        total_cost_usd=0.05,
    )
    fields.update(overrides)
    return ResultMessage(**fields)


class FakeQuery:
    """Stands in for claude_agent_sdk.query and records how it was called."""

    def __init__(self, messages):
        self.messages = messages
        self.calls = []

    def __call__(self, *, prompt, options):
        self.calls.append((prompt, options))

        async def gen():
            for m in self.messages:
                yield m

        return gen()


@pytest.fixture
def fake_query(monkeypatch):
    def install(messages):
        fq = FakeQuery(messages)
        monkeypatch.setattr(tailor, "query", fq)
        return fq

    return install


async def test_tailor_success_with_job_text(fake_query, sample_resume_md, sample_job_text):
    fq = fake_query([AssistantMessage(content=[TextBlock(text="Working on it")], model="m"), make_result()])
    progress = []

    result = await tailor_resume(sample_resume_md, job_text=sample_job_text, on_progress=progress.append)

    assert result.company == "Maple Commerce"
    assert result.match_score == 82
    assert result.missing_keywords == ["dbt", "Snowflake"]
    assert result.tailored_resume_markdown.startswith("# Alex Rivera")
    assert progress == ["Working on it"]

    prompt, options = fq.calls[0]
    assert "Northwind Retail" in prompt and "Maple Commerce" in prompt
    assert options.tools == []  # no tools at all when the posting is given as text
    assert options.setting_sources == []
    assert options.permission_mode == "dontAsk"
    assert options.output_format["type"] == "json_schema"


async def test_tailor_with_url_enables_only_webfetch(fake_query, sample_resume_md):
    fq = fake_query(
        [
            AssistantMessage(content=[ToolUseBlock(id="1", name="WebFetch", input={"url": "u"})], model="m"),
            make_result(),
        ]
    )
    progress = []
    await tailor_resume(sample_resume_md, job_url="https://example.com/job", on_progress=progress.append)

    prompt, options = fq.calls[0]
    assert "https://example.com/job" in prompt
    assert options.tools == ["WebFetch"]
    assert options.allowed_tools == ["WebFetch"]
    assert progress == ["Using tool: WebFetch"]


async def test_tailor_raises_on_agent_error(fake_query, sample_resume_md):
    fake_query([make_result(subtype="error_max_turns", is_error=True, structured_output=None, result=None)])
    with pytest.raises(TailoringError, match="error_max_turns"):
        await tailor_resume(sample_resume_md, job_text="job")


async def test_tailor_raises_when_no_resume_produced(fake_query, sample_resume_md):
    fake_query([make_result(structured_output={**STRUCTURED, "tailored_resume_markdown": "", "notes": "403"})])
    with pytest.raises(TailoringError, match="403"):
        await tailor_resume(sample_resume_md, job_url="https://example.com/job")


def test_build_prompt_requires_exactly_one_job_source():
    with pytest.raises(ValueError):
        build_prompt("resume")
    with pytest.raises(ValueError):
        build_prompt("resume", job_text="a", job_url="b")
    assert "Keep it to one page" in build_prompt("r", job_text="j", extra_instructions="Keep it to one page")


def test_auth_warning(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert auth_warning() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert "subscription" in auth_warning()


def test_cli_end_to_end_writes_md_docx_pdf(fake_query, tmp_path: Path, sample_resume_docx: Path, sample_job_text: str):
    fake_query([make_result()])
    job = tmp_path / "job.txt"
    job.write_text(sample_job_text, encoding="utf-8")
    out = tmp_path / "output"

    code = cli.main(
        ["tailor", "--resume", str(sample_resume_docx), "--job-file", str(job), "--out", str(out), "--quiet"]
    )

    assert code == 0
    folders = list(out.iterdir())
    assert len(folders) == 1 and folders[0].name.endswith("_Maple-Commerce_Senior-Data-Analyst")
    names = {p.name for p in folders[0].iterdir()}
    assert "Alex_Rivera_Resume_Maple_Commerce.md" in names
    assert "Alex_Rivera_Resume_Maple_Commerce.docx" in names
    assert "tailoring_report.md" in names
    report = (folders[0] / "tailoring_report.md").read_text()
    assert "dbt" in report and "82/100" in report
    if _find_soffice():
        assert "Alex_Rivera_Resume_Maple_Commerce.pdf" in names


def test_cli_rejects_unknown_format(capsys):
    with pytest.raises(SystemExit):
        cli.main(["tailor", "--resume", "r.docx", "--job-text", "j", "--formats", "docx,rtf"])


def test_cli_render_command(tmp_path: Path):
    md = tmp_path / "Jane_Resume.md"
    md.write_text("# Jane Doe\njane@example.com\n\n## Skills\n- SQL\n", encoding="utf-8")
    assert cli.main(["render", str(md), "--formats", "docx"]) == 0
    assert (tmp_path / "Jane_Resume.docx").exists()
