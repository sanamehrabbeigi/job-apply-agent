# Roadmap

Where this project is going next. The goal: **an agent that finds the jobs that fit me
best across job sites, prepares a strong, truthful application for each, and helps me
apply, with me in control of what gets sent.**

## Done

- [x] **Resume tailoring.** Master resume + job posting → tailored resume (Markdown, Word,
  PDF) and a report with match score, gaps and questions.
- [x] **Job links.** Any LinkedIn job link, and most company career pages, are fetched
  and saved to `data/jobs/`.
- [x] **Career profile.** Extra documents in `data/profile/` that the agent can draw on.
- [x] **Ask-then-rewrite loop.** The agent targets a match score (85 by default), asks about
  gaps, saves the answers, and rewrites with them.
- [x] **Local web app.** `job-agent serve`: FastAPI backend + React/TypeScript UI.
- [x] **Job search.** Greenhouse, Lever, Ashby, Workday, JSearch, Adzuna and LinkedIn guest search,
  deduplicated in SQLite, with a relevance gate and free-tier quota budgets.
- [x] **Claude ranking.** Every relevant job scored by Claude Haiku 5.5 with reasons and gaps.
- [x] **Schedule + tracker.** Per-source intervals while the app is open; status and notes per job.

---

## Phase 2: Find and rank the best jobs for me (done)

Built as described below, as a local web app. Glassdoor and Indeed listings arrive through
JSearch (Google for Jobs); there is no direct connector for them.

**Goal:** the agent searches several job sources and shows me a ranked shortlist of the
jobs that best match my profile, with a short reason for each. I pick which ones to
apply to.

### 2.1 My job preferences

A `data/preferences.yaml` file the agent uses for searching and filtering:

```yaml
titles: [Data Analyst, Product Analyst, Business Intelligence Analyst, Data Scientist]
locations: [Toronto, Remote (Canada)]
work_type: [hybrid, remote, on-site]
employment: [full-time]
seniority: [entry, associate, mid]
exclude_companies: []
must_not_require: ["10+ years", "PhD"]
salary_min_cad: null
posted_within_days: 7
```

### 2.2 Job sources

| Source | How | Status / risks |
| --- | --- | --- |
| **Company career pages** | Public job-board APIs of the hiring systems many companies use: Greenhouse, Lever, Ashby, SmartRecruiters, and Workday career sites. I keep a list of target companies. | Best option: these feeds are meant to be public. Each system has its own format. |
| **Indeed** | An Indeed connector (MCP server) for job search, if available to my Claude account. | To verify: whether it works through the Agent SDK with my subscription, and its limits. |
| **LinkedIn** | Public, logged-out job search pages, at a slow pace, a few times a day at most. | LinkedIn's terms restrict automated access, and it may block requests. My LinkedIn account is never used for this. |
| **Glassdoor** | No good option known yet. | To research: I believe Glassdoor closed its public API, and the site blocks bots. Its listings may overlap with Indeed's. |
| **Job aggregator APIs** (e.g. Adzuna, or paid APIs that cover Google for Jobs) | Official APIs with keys. | To research: coverage in Canada, cost, and whether they include LinkedIn, Indeed and Glassdoor listings. |

All fetched jobs are stored in a local database (SQLite in `data/`), with duplicates merged
(the same job is often posted on several sites), so each job is shown once.

### 2.3 Matching and ranking

To keep within my Claude Pro usage limits, the work is done in stages:

1. **Hard filters (free):** location, work type, seniority, posting age, excluded companies,
   "must not require" phrases.
2. **Quick scoring (cheap):** keyword overlap between each job and my resume + profile;
   keep the top ~30.
3. **Claude scoring (top jobs only):** Claude reads each remaining posting with my profile
   and gives a match score, the 3 strongest reasons I fit, and the main gaps.
4. **Shortlist:** a daily digest (Markdown/HTML page) with the top 10, each with a link,
   score, reasons, gaps, and a one-command "tailor my resume for this" step.

### 2.4 Running it

- `job-agent search` to run on demand; `job-agent shortlist` to view the latest results.
- Optional daily run with Windows Task Scheduler (or cron on Mac/Linux) on my computer.
- An **application tracker** in the same database: status of each job (new, shortlisted,
  applied, interview, rejected, offer), the date, and which resume version was sent.

**Done when:** one command gives me a ranked list of fresh, relevant jobs from at least
three sources, and I can go from a shortlisted job to a tailored resume in one step.

---

## Phase 3: Help me apply

**Goal:** applying to a shortlisted job takes minutes, and nothing is ever sent
without my review.

### 3.1 Application kit (no automation risk)

For each chosen job, the agent prepares a folder with:

- the tailored resume (Word + PDF);
- a **cover letter** in my voice (learned from samples I provide), truthful and specific to
  the company;
- **answers to the application's questions** ("Why this company?", work authorization,
  salary expectations, notice period...), drawn from a reusable **answer bank** in
  `data/profile/` that grows as I answer new questions;
- a short checklist and the link to apply.

### 3.2 Assisted form filling (human in the loop)

- The agent opens the application form in a browser (Playwright, or Claude in Chrome),
  fills in my details, uploads the resume and cover letter, and answers the questions
  from the answer bank.
- It **stops before submitting**: I review every field and click "Submit" myself.
- Start with the systems with predictable forms (Greenhouse, Lever, Ashby), then Workday.
- The tracker is updated when I confirm the application was sent.

### 3.3 Fully automatic applying: not planned (for now)

Submitting applications without my review is deliberately **out of scope**:

- **Account risk:** LinkedIn (including Easy Apply) and other job sites forbid automated
  applying and may restrict or ban accounts that do it.
- **Quality risk:** a wrong answer (salary, work authorization, a misread question) sent
  automatically can cost me the job and can't be taken back.
- **Practical blockers:** CAPTCHAs, logins and one-off forms.

This can be revisited later for specific company career sites, once assisted filling has
proven reliable, and only with a final confirmation from me per application.

**Done when:** for a shortlisted job, I get a complete application kit and a pre-filled
form, and applying takes me only a review and one click.

---

## Ongoing principles

- **Honesty:** every resume, cover letter and answer uses only true facts from my
  documents and answers. A gap is reported, never invented.
- **Privacy:** personal documents, jobs and the database stay in `data/` on my computer,
  outside git.
- **Respect site rules:** prefer official or public APIs. Use any website scraping
  slowly and for personal use only, and never automate my personal accounts on job sites.
- **I stay in control:** the agent suggests and prepares; I decide and submit.

## Open questions

- Which target companies should the career-page search start with?
- Which aggregator API (if any) is worth paying for?
- Do I want the daily shortlist by email, as a web page, or in the terminal?
- Which answers belong in the answer bank first (work authorization, salary range,
  availability)?
