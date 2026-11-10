import pytest

from job_apply_agent.jobs import JobPosting
from job_apply_agent.preferences import merge_defaults
from job_apply_agent.search.dedupe import canonical_url, dedupe_key, normalize_company, normalize_title
from job_apply_agent.search.filters import evaluate, location_label, role_matches

PREFS = merge_defaults({})


def job(title="Data Analyst", location="Toronto, ON", **kw) -> JobPosting:
    return JobPosting(url="https://x/1", title=title, company=kw.pop("company", "Acme"), location=location, **kw)


@pytest.mark.parametrize(
    ("title", "ok"),
    [
        ("Senior Data Analyst II", True),
        ("Analytics Engineer", True),
        ("BI Developer (Power BI)", True),
        ("Head of Analytics", True),
        ("Data Scientist, Pricing", True),
        ("Machine Learning Engineer", False),
        ("Software Engineer, Big Data Platform", False),
        ("Account Executive", False),
    ],
)
def test_role_terms(title, ok):
    assert role_matches(title, PREFS["role_terms"]) is ok


@pytest.mark.parametrize(
    ("location", "remote", "country", "label"),
    [
        ("Toronto, ON", None, "", "Toronto/GTA"),
        ("Toronto, CA", None, "", "Toronto/GTA"),
        ("Mississauga, Ontario", None, "", "Toronto/GTA"),
        ("Kanata, Ontario - Canada", None, "", "Ottawa"),
        ("Remote (Canada)", True, "Canada", "Remote (Canada)"),
        ("Canada - Remote (ON, AB, BC, or NS Only)", None, "", "Remote (Canada)"),
        ("Remote (United States | Canada)", None, "", "Remote (Canada)"),
        ("KOHO (CAN)", True, "", "Remote (Canada)"),
        ("Canada", None, "", "Remote (Canada)"),
        ("Remote", True, "CA", "Remote (Canada)"),
        ("Remote - US", True, "", None),
        ("San Francisco, CA", None, "", None),
        ("Vancouver, BC", None, "", None),
        ("Montréal, QC", False, "Canada", None),
        ("3 Locations", None, "", None),
        ("", None, "", "Unknown"),
    ],
)
def test_location_cases(location, remote, country, label):
    assert location_label(job(location=location, remote=remote, country=country), PREFS["locations"]) == label


def test_evaluate_combines_role_location_and_exclusions():
    assert evaluate(job(), PREFS) == (True, "Toronto/GTA")
    assert evaluate(job(title="Recruiter"), PREFS) == (False, "")
    assert evaluate(job(location="Austin, TX"), PREFS) == (False, "")
    excluded = merge_defaults({"excluded_companies": ["ACME Inc."]})
    assert evaluate(job(), excluded) == (False, "")
    no_unknown = merge_defaults({"locations": {"include_unknown": False}})
    assert evaluate(job(location=""), no_unknown) == (False, "")


def test_normalizers():
    assert normalize_company("Wealthsimple Technologies Inc.") == "wealthsimple technologies"
    assert normalize_company("TD Bank, Ltd") == "td bank"
    assert normalize_title("Sr. Data Analyst (Remote)") == "senior data analyst"
    assert normalize_title("Data Analyst - Toronto") == "data analyst"
    assert canonical_url("https://Boards.Greenhouse.io/faire/jobs/88?gh_jid=88#x") == "boards.greenhouse.io/faire/jobs/88?gh_jid=88"
    assert canonical_url("not a url") == ""


def test_dedupe_key_merges_variants():
    a = job(title="Senior Data Analyst", company="Acme Inc.", location="Toronto, Ontario, Canada")
    b = job(title="Sr. Data Analyst (Hybrid)", company="ACME", location="Toronto, ON")
    c = job(title="Data Analyst", company="Acme", location="Toronto, ON")
    d = job(title="Senior Data Analyst", company="Acme", location="Montréal, QC")
    assert dedupe_key(a) == dedupe_key(b)
    assert dedupe_key(a) != dedupe_key(c)  # seniority kept
    assert dedupe_key(a) != dedupe_key(d)  # city kept
    assert dedupe_key(d).endswith("|montreal")


def test_canonical_url_keeps_job_id_query_and_drops_tracking():
    a = canonical_url("https://stripe.com/jobs/search?gh_jid=111&utm_source=x")
    b = canonical_url("https://stripe.com/jobs/search?gh_jid=222")
    assert a == "stripe.com/jobs/search?gh_jid=111" and a != b
    assert canonical_url("https://jobs.lever.co/acme/a1?lever-source=LinkedIn") == "jobs.lever.co/acme/a1"


def test_remote_jobs_in_different_countries_do_not_merge():
    us = job(title="Data Engineer", location="Remote - US", remote=True)
    ca = job(title="Data Engineer", location="Remote - Canada", remote=True)
    assert dedupe_key(us) != dedupe_key(ca)
