import re

from test_tailor import make_result

from job_apply_agent.search import scoring
from job_apply_agent.search.scoring import build_options, profile_hash, score_jobs, trim_description

JOBS = [{"id": i, "title": f"Data Analyst {i}", "company": "Acme", "location": "Toronto", "description": "SQL. " * 20}
        for i in range(1, 8)]


class ScoringQuery:
    """Fake SDK query: scores every <job id="N"> in the prompt; can fail chosen calls."""

    def __init__(self, fail_calls=(), error_text="boom"):
        self.prompts = []
        self.fail_calls = set(fail_calls)
        self.error_text = error_text

    def __call__(self, *, prompt, options):
        self.prompts.append((prompt, options))
        call_no = len(self.prompts)
        ids = [int(x) for x in re.findall(r'<job id="(\d+)">', prompt)]

        async def gen():
            if call_no in self.fail_calls:
                yield make_result(subtype="error_during_execution", is_error=True, structured_output=None,
                                  result=self.error_text)
                return
            yield make_result(structured_output={"results": [
                {"job_id": i, "score": 70 + i, "summary": f"fit {i}", "reasons": ["SQL", "dashboards", "x", "y"],
                 "gaps": ["dbt"], "seniority_fit": "fit"} for i in ids
            ] + [{"job_id": 999, "score": 1, "summary": "", "reasons": [], "gaps": [], "seniority_fit": "fit"}]})

        return gen()


def test_profile_hash_tracks_resume_and_profile_but_not_answers():
    base = profile_hash("resume", "profile")
    assert len(base) == 16
    assert base != profile_hash("resume2", "profile")
    assert base != profile_hash("resume", "profile2")


def test_trim_description_cuts_late_boilerplate_only():
    text = "About us\nWe build things.\n" + "Requirements: SQL.\n" * 30 + "Benefits\nDental.\nEqual opportunity employer."
    trimmed = trim_description(text)
    assert trimmed.startswith("About us") and "Requirements" in trimmed and "Dental" not in trimmed
    assert trim_description("x" * 9000, limit=100).endswith("…")


def test_options_are_locked_down():
    options = build_options("claude-haiku-5-5")
    assert options.model == "claude-haiku-5-5" and options.tools == [] and options.setting_sources == []
    assert options.permission_mode == "dontAsk" and options.output_format["type"] == "json_schema"


async def test_score_jobs_batches_and_parses():
    fq = ScoringQuery()
    progress = []
    outcome = await score_jobs(JOBS, resume="R", profile="P", answers="A", model="m", batch_size=3,
                               concurrency=1, on_progress=lambda done, total: progress.append((done, total)),
                               query_fn=fq)
    assert len(fq.prompts) == 3  # 3 + 3 + 1
    assert sorted(s.job_id for s in outcome.scores) == list(range(1, 8))  # stray id 999 ignored
    assert outcome.scores[0].reasons == ["SQL", "dashboards", "x"]  # capped at 3
    assert progress[-1] == (7, 7) and not outcome.failed
    prompt = fq.prompts[0][0]
    assert "<candidate_resume>\nR\n</candidate_resume>" in prompt and "Data Analyst 1" in prompt


async def test_failed_batch_leaves_jobs_unscored():
    outcome = await score_jobs(JOBS, resume="R", profile="", answers="", model="m", batch_size=3, concurrency=1,
                               query_fn=ScoringQuery(fail_calls={2}))
    assert sorted(outcome.failed) == [4, 5, 6] and len(outcome.scores) == 4
    assert outcome.usage_limited is False and "boom" in outcome.errors[0]


async def test_usage_limit_stops_remaining_batches():
    fq = ScoringQuery(fail_calls={1}, error_text="Claude AI usage limit reached|1731200000")
    outcome = await score_jobs(JOBS, resume="R", profile="", answers="", model="m", batch_size=3, concurrency=1,
                               query_fn=fq)
    assert outcome.usage_limited is True and len(fq.prompts) == 1
    assert sorted(outcome.failed) == list(range(1, 8)) and outcome.scores == []


async def test_default_query_is_looked_up_at_call_time(monkeypatch):
    fq = ScoringQuery()
    monkeypatch.setattr(scoring, "query", fq)
    outcome = await score_jobs(JOBS[:1], resume="R", profile="", answers="", model="m")
    assert len(outcome.scores) == 1


async def test_auth_failure_stops_remaining_batches():
    fq = ScoringQuery(fail_calls={1}, error_text="Failed to authenticate: OAuth session expired and could not be refreshed")
    outcome = await score_jobs(JOBS, resume="R", profile="", answers="", model="m", batch_size=3, concurrency=1,
                               query_fn=fq)
    assert outcome.auth_failed is True and len(fq.prompts) == 1 and outcome.scores == []
