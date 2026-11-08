from pathlib import Path

import pytest

from job_apply_agent import jobs
from job_apply_agent.jobs import JobFetchError, fetch_job, linkedin_job_id, parse_json_ld, parse_linkedin

DESCRIPTION = "<p><strong>About the role</strong></p><p>We need an analyst.</p><ul><li>SQL</li><li>Power BI</li></ul>" * 8

LINKEDIN_PAGE = f"""
<h2 class="top-card-layout__title font-sans">Data Analyst</h2>
<a class="topcard__org-name-link topcard__flavor--black-link" href="#">  Example Co </a>
<span class="topcard__flavor topcard__flavor--bullet">Toronto, Ontario, Canada</span>
<div class="show-more-less-html__markup relative">{DESCRIPTION}</div>
<li><h3 class="description__job-criteria-subheader">Seniority level</h3>
<span class="description__job-criteria-text">Associate</span></li>
<li><h3 class="description__job-criteria-subheader">Employment type</h3>
<span class="description__job-criteria-text"> Full-time </span></li>
"""

JSON_LD_PAGE = """<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@type": "JobPosting", "title": "Product Analyst",
 "hiringOrganization": {"@type": "Organization", "name": "Acme"},
 "employmentType": ["FULL_TIME"],
 "jobLocation": {"@type": "Place", "address": {"addressLocality": "Toronto", "addressRegion": "ON"}},
 "description": "&lt;p&gt;Own product analytics.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;/ul&gt;"}
</script></head><body>ignored</body></html>"""


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/4470022823/",
        "https://ca.linkedin.com/jobs/view/data-analyst-at-exacare-ai-4470022823?trk=abc",
        "https://www.linkedin.com/jobs/search-results/?currentJobId=4470022823&keywords=data%20analyst&geoId=1",
        "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4470022823",
    ],
)
def test_linkedin_job_id_from_any_link(url):
    assert linkedin_job_id(url) == "4470022823"


def test_linkedin_job_id_ignores_other_sites():
    assert linkedin_job_id("https://boards.greenhouse.io/acme/jobs/4470022823") is None


def test_parse_linkedin():
    posting = parse_linkedin(LINKEDIN_PAGE, "https://www.linkedin.com/jobs/view/1/")
    assert (posting.title, posting.company, posting.location) == ("Data Analyst", "Example Co", "Toronto, Ontario, Canada")
    assert posting.details == {"Seniority level": "Associate", "Employment type": "Full-time"}
    assert "About the role" in posting.description and "- Power BI" in posting.description
    text = posting.to_text()
    assert text.startswith("Source: https://www.linkedin.com/jobs/view/1/\nJob title: Data Analyst")


def test_parse_json_ld():
    posting = parse_json_ld(JSON_LD_PAGE, "https://acme.example/jobs/1")
    assert posting.title == "Product Analyst" and posting.company == "Acme"
    assert posting.location == "Toronto, ON"
    assert posting.details["Employment type"] == "FULL_TIME"
    assert posting.description == "Own product analytics.\n\n- SQL"


def test_fetch_job_uses_linkedin_guest_page_and_saves(monkeypatch, tmp_path: Path):
    requested = []
    monkeypatch.setattr(jobs, "_http_get", lambda url, timeout: requested.append(url) or LINKEDIN_PAGE)
    posting = fetch_job("https://www.linkedin.com/jobs/search-results/?currentJobId=4470022823&x=1")
    assert requested == ["https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4470022823"]
    path = posting.save(tmp_path)
    assert path.name == "example-co_data-analyst_4470022823.txt"
    assert "Job title: Data Analyst" in path.read_text()


def test_fetch_job_rejects_pages_without_a_description(monkeypatch):
    monkeypatch.setattr(jobs, "_http_get", lambda url, timeout: "<html><body>Please log in</body></html>")
    with pytest.raises(JobFetchError):
        fetch_job("https://careers.example.com/job/1")
