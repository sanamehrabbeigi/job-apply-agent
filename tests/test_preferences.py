from pathlib import Path

import pytest

from job_apply_agent import envfile, paths, preferences
from job_apply_agent.preferences import (
    DEFAULT_PREFERENCES,
    load_preferences,
    merge_defaults,
    resume_path,
    save_preferences,
    validate_preferences,
)


def test_paths_follow_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("JOB_AGENT_OUTPUT_DIR", str(tmp_path / "o"))
    assert paths.data_dir() == tmp_path / "d"
    assert paths.profile_dir() == tmp_path / "d" / "profile"
    assert paths.db_path() == tmp_path / "d" / "app.db"
    assert paths.output_dir() == tmp_path / "o"


def test_defaults_when_file_missing(tmp_path: Path):
    prefs = load_preferences(tmp_path / "missing.yaml")
    assert prefs == merge_defaults({})
    assert "machine learning engineer" not in prefs["role_terms"]
    assert "analytics engineer" in prefs["role_terms"]
    assert prefs["models"]["scoring"] == "claude-haiku-5-5"
    assert prefs["sources"]["jsearch"]["budget"] == 180


def test_user_values_override_defaults_and_lists_replace():
    merged = merge_defaults({"role_terms": ["data analyst"], "sources": {"linkedin": {"enabled": False}}})
    assert merged["role_terms"] == ["data analyst"]
    assert merged["sources"]["linkedin"]["enabled"] is False
    assert merged["sources"]["linkedin"]["interval_hours"] == DEFAULT_PREFERENCES["sources"]["linkedin"]["interval_hours"]
    assert merged["sources"]["greenhouse"]["enabled"] is True


def test_save_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "prefs.yaml"
    prefs = merge_defaults({"excluded_companies": ["Acme"]})
    save_preferences(prefs, path)
    assert load_preferences(path)["excluded_companies"] == ["Acme"]


@pytest.mark.parametrize(
    "bad",
    [
        {"role_terms": []},
        {"sources": {"monster": {"enabled": True}}},
        {"sources": {"lever": {"interval_hours": 0}}},
        {"target_score": 150},
        {"models": {"scoring": ""}},
    ],
)
def test_validate_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        validate_preferences(merge_defaults(bad))


def test_resume_path_default_and_custom(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("JOB_AGENT_DATA_DIR", str(tmp_path))
    assert resume_path(merge_defaults({})) == tmp_path / "my_resume.docx"
    assert resume_path(merge_defaults({"resume_path": "/x/cv.md"})) == Path("/x/cv.md")


def test_env_file_and_environment(monkeypatch, tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text('# keys\nJSEARCH_API_KEY="abc"\nexport ADZUNA_APP_ID=id1\nnot a line\n', encoding="utf-8")
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    monkeypatch.setenv("ADZUNA_APP_ID", "from-env")
    values = envfile.load_env(env)
    assert values["JSEARCH_API_KEY"] == "abc"
    assert values["ADZUNA_APP_ID"] == "from-env"  # real environment wins
    assert envfile.read_env_file(tmp_path / "none") == {}


def test_preferences_module_exposes_source_names():
    assert preferences.SOURCE_NAMES == ("greenhouse", "lever", "ashby", "workday", "jsearch", "adzuna", "linkedin")
