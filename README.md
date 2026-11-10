# job-apply-agent

A personal AI agent that helps you apply to jobs, built on the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview) (Python).

**What it does:**

- **Finds jobs for you.** On demand or on a schedule, it searches Canadian company career sites
  (Greenhouse, Lever, Ashby, Workday), JSearch (Google for Jobs: LinkedIn, Indeed, Glassdoor...),
  Adzuna and LinkedIn's public job search for Data Analyst, Data Scientist and Data Engineer roles
  in Toronto/GTA, Remote (Canada) and Ottawa.
- **Ranks every job by fit.** Claude Haiku 5.5 reads each relevant posting with your resume and
  profile and gives a match score, the reasons you fit, and the gaps.
- **Tailors your resume** to any job in one click: Markdown, Word (.docx) and PDF, plus a report
  of what changed and what's missing. It asks you about gaps and never invents experience.

> **Honesty by design:** the agent is told never to invent employers, titles, dates,
> skills or metrics. If the job asks for something your resume doesn't show, the agent
> lists it in the report and doesn't add it. It may also ask you questions in case you
> have that experience but didn't write it down.

## How it works

```
master resume (.docx) ──pandoc──► Markdown ─┐
job posting (file / text / URL) ────────────┼─► Claude (Agent SDK, structured JSON output)
                                            │
                    tailored Markdown ◄─────┘
                         ├──resume renderer (python-docx)──► .docx
                         └──LibreOffice / MS Word──────────► .pdf
                    + tailoring_report.md (match score, matched/missing skills, questions)
```

- The agent's tools are locked down: it has **no file or shell access**. Its only possible
  tool is `WebFetch`, and only when you pass `--job-url`.
- It doesn't load your personal `~/.claude` settings or `CLAUDE.md` files (`setting_sources=[]`).
- The Word/PDF output uses a clean, classic single-column layout that ATS systems parse
  well: centered name, ruled section headings, right-aligned dates, compact bullets.
  Page margins are copied from your original resume. Your original's exact design
  (custom fonts, tables, columns) is not copied.

## Requirements

- Python 3.10+
- A Claude **Pro, Max, Ultra, Team or Enterprise** subscription, **or** an Anthropic API key
- For PDF output: [LibreOffice](https://www.libreoffice.org/download/) (free, any OS), **or**
  Microsoft Word on Windows/macOS together with `pip install -e ".[word]"`

Pandoc is bundled with the `pypandoc-binary` dependency, and the Claude Code engine is
bundled with `claude-agent-sdk`. You don't need to install either one separately.

## Setup

```bash
git clone https://github.com/sanamehrabbeigi/job-apply-agent.git
cd job-apply-agent
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e .
```

The `claude-agent-sdk` wheel is about 150 MB because it bundles the Claude Code engine.

### Authenticate with your Claude subscription

The Agent SDK runs the Claude Code engine and uses the same credentials. Pick one:

1. **Log in once with Claude Code** (easiest on your own computer). Install the
   [Claude Code CLI](https://code.claude.com/docs/en/setup), run `claude`, and log in with
   your claude.ai account. The agent reuses that login.
2. **Use a long-lived token** (for servers, scripts or CI):
   ```bash
   claude setup-token                       # opens the browser, prints a 1-year token
   export CLAUDE_CODE_OAUTH_TOKEN=<token>   # keep it secret; never commit it
   ```

Make sure `ANTHROPIC_API_KEY` is **not** set. If it is, it takes precedence over your
subscription and you are billed per token on the API. The CLI warns you when it's set.

> **Note on terms:** Anthropic's Agent SDK docs say that third-party developers may not
> offer claude.ai login or rate limits in products they ship to *other people*. This
> project is meant to run for **you only**, with your own subscription. If you ever turn
> it into a service for others, switch to API-key authentication. Check the current
> [Agent SDK docs](https://code.claude.com/docs/en/agent-sdk/overview) and Anthropic's
> terms yourself, because they can change.

Tailoring a resume uses your subscription's normal usage limits, which are shared with
claude.ai. One run is a single, fairly short request.

## The app

```bash
job-agent serve            # opens http://127.0.0.1:8000 in your browser
```

- **New (24h)** and **All jobs** tabs, both ranked by match score. Click a column to re-sort;
  filter by role, location, source, status or minimum score.
- Click a job for the score, reasons, gaps, full description and links. Set its status
  (saved, applied, interview...), add notes, or click **Tailor my resume for this job**.
- **Search now** runs every enabled source. While the app is open it also searches on a
  schedule: company sites hourly, JSearch daily, Adzuna every 8 hours, LinkedIn twice a day.
  Change this in **Settings**, where you also upload your resume and profile documents, edit the
  job title terms, locations and excluded companies, and manage the company list.

Run a search without the UI (for cron or Task Scheduler):

```bash
job-agent search                         # all enabled sources, then Claude scoring
job-agent search --sources greenhouse,lever --no-score
```

### Optional API keys (free tiers)

Create `data/.env` (git-ignored):

```bash
JSEARCH_API_KEY=...      # https://rapidapi.com -> JSearch, Basic (free) plan
ADZUNA_APP_ID=...        # https://developer.adzuna.com -> free key
ADZUNA_APP_KEY=...
```

Without keys those two sources are skipped and everything else works. The app counts calls and
stops at a budget under each free tier (JSearch 180/month, Adzuna 100/day; editable in
`data/preferences.yaml`).

### How searching stays light on your Claude usage

Only jobs whose title matches your role terms and whose location is in your target areas are
scored, and each job is scored once (again only if you change your resume or profile).
Scoring uses Claude Haiku 5.5, the smallest current model.

## Usage

### 1. Add your documents

(You can also upload them in the app's **Settings**. Once a resume is set there, `--resume` is optional.)

```
data/
  my_resume.docx          # your current resume (the starting point)
  profile/                # your career profile: anything with more detail
    work_history.docx     #   full job history, every project and achievement
    skills.md             #   tools, certificates, courses...
    answers.md            #   created by the agent: your answers to its questions
  jobs/                   # job postings fetched from links (created automatically)
```

The agent can use **any fact** from `data/profile/` (Word, Markdown or text files), even
if it's not in your resume, and picks what fits each job. The `data/` and `output/`
folders and all `.docx`/`.pdf` files are git-ignored, so your personal information is
never committed.

### 2. Tailor to a job link

```bash
job-agent tailor --resume data/my_resume.docx --job-url "https://www.linkedin.com/jobs/view/4470022823/"
```

Any LinkedIn job link works, including links copied from search results
(`...search-results/?currentJobId=...`). Company career pages (Greenhouse, Lever,
Workday and most others) work too. The posting is saved in `data/jobs/`.

### 3. Answer its questions to raise the match

The agent aims for a **match score of 85** (change it with `--target-score`):

1. It rewrites your resume in the job's language, using only true facts from your
   resume, profile and earlier answers.
2. If the score is below the target, it asks you short questions about the gaps
   ("Have you used Looker? If yes, I'll add it to Skills"). Answer truthfully, or press
   Enter to skip.
3. It rewrites again with your answers, up to 3 rounds (`--max-rounds`).

Your answers are saved in `data/profile/answers.md` and reused for every future job, so
the agent learns your background over time. If a gap is real, the score stays below the
target; the agent never invents experience to close it.

### Other options

```bash
# Job posting from a text file, or pasted as text
job-agent tailor --resume data/my_resume.docx --job-file data/jobs/acme_data_analyst.txt
job-agent tailor --resume data/my_resume.docx --job-text "Data Analyst at ..."

# Just save a posting from a link
job-agent fetch-job "https://www.linkedin.com/jobs/view/4470022823/"

# One rewrite without questions, two pages, a specific model
job-agent tailor --resume data/my_resume.docx --job-url URL --no-questions \
  --instructions "Two pages are fine." --model opus
```

> **LinkedIn note:** the agent reads LinkedIn's public (logged-out) job page, so your
> LinkedIn account is never used. LinkedIn's User Agreement restricts automated access,
> so keep it to personal, occasional use. If LinkedIn stops returning a posting, copy the
> text into a file and use `--job-file`.

Try it with the fictional example files:

```bash
job-agent tailor --resume examples/sample_resume.md --job-file examples/sample_job.txt
```

Output (in `output/<date>_<company>_<job-title>/`):

| File | What it is |
| --- | --- |
| `<Name>_Resume_<Company>.md` | Tailored resume (Markdown, easy to edit) |
| `<Name>_Resume_<Company>.docx` | Word version |
| `<Name>_Resume_<Company>.pdf` | PDF version |
| `tailoring_report.md` | Match score, matched/missing requirements, changes, questions for you |

**Always read the tailored resume before sending it.** Make sure every line is true and
sounds like you. If you want to change something, edit the `.md` file and rebuild the
Word/PDF files:

```bash
job-agent render output/<folder>/<Name>_Resume_<Company>.md --reference data/my_resume.docx
```

## Development

```bash
pip install -e ".[dev]"
ruff check src tests
pytest

cd frontend
npm install
npm test
npm run dev        # UI on http://localhost:5173, proxied to `job-agent serve` on :8000
npm run build      # writes the production UI into src/job_apply_agent/web/static/
```

The tests don't call Claude or any job site: the SDK and HTTP calls are faked, and the
document conversions run for real. The built UI is committed, so running the app needs only
Python.

## Project layout

```
src/job_apply_agent/
  cli.py        # `job-agent` command
  tailor.py     # Agent SDK call (options, prompt, structured output)
  prompts.py    # System prompt + JSON schema for the result
  jobs.py       # Fetch job postings from links (LinkedIn, JSON-LD job pages)
  career_profile.py  # Load data/profile/ documents, save your answers
  documents.py  # DOCX -> Markdown (pandoc), DOCX -> PDF (LibreOffice / Word)
  render.py     # Markdown -> styled resume .docx
  tailor_flow.py     # Ask-then-rewrite loop shared by the CLI and the app
  tailor_sessions.py # Tailoring started from the browser
  db.py         # SQLite: jobs, links per source, runs, quotas (data/app.db)
  preferences.py# data/preferences.yaml (roles, locations, sources, models)
  runtime.py    # Wires the database, search runner and scheduler together
  search/       # Sources, relevance gate, dedupe, Claude scoring, pipeline, scheduler
  web/          # FastAPI app + built UI (static/)
frontend/       # React + TypeScript UI source (Vite)
examples/       # Fictional resume and job posting for trying it out
tests/
```

## Roadmap

See **[ROADMAP.md](ROADMAP.md)** for what's next:

- **Phase 2: find and rank the best jobs.** Done: the app searches job sites and ranks every
  relevant job with Claude.
- **Phase 3: help me apply.** Application kit (resume, cover letter, answers to
  application questions), then assisted form filling where I review and click "Submit".
