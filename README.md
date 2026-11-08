# job-apply-agent

A personal AI agent that helps you apply to jobs, built on the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview) (Python).

**Phase 1 feature: resume tailoring.** Give it your general (master) resume and a job
posting. It writes a resume tailored to that job, using only your real experience, and
saves it as Markdown, Word (.docx) and PDF, plus a report of what it changed and what's
missing.

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

## Usage

Put your real resume in `data/`. The `data/` and `output/` folders and all `.docx`/`.pdf`
files are git-ignored, so your personal information is never committed.

```bash
# Job posting saved as a text file (most reliable)
job-agent tailor --resume data/my_resume.docx --job-file data/jobs/acme_data_analyst.txt

# Job posting URL (works for many company career pages; LinkedIn and some sites block bots)
job-agent tailor --resume data/my_resume.docx --job-url https://example.com/careers/123

# Options
job-agent tailor --resume data/my_resume.docx --job-file job.txt \
  --formats docx,pdf \
  --instructions "Keep it to one page. Emphasize experimentation." \
  --model opus
```

Try it with the fictional example files:

```bash
job-agent tailor --resume examples/sample_resume.md --job-file examples/sample_job.txt
```

Output (in `output/<date>_<company>_<job-title>/`):

| File | What it is |
| --- | --- |
| `<Name>_Resume_<Company>.md` | Tailored resume (Markdown, easy to edit) |
| `<Name>_Resume_<Company>.docx` | Word version, styled like your original |
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
pytest
```

The tests don't call Claude: the SDK call is mocked, and the document conversions run for real.

## Project layout

```
src/job_apply_agent/
  cli.py        # `job-agent` command
  tailor.py     # Agent SDK call (options, prompt, structured output)
  prompts.py    # System prompt + JSON schema for the result
  documents.py  # DOCX -> Markdown (pandoc), DOCX -> PDF (LibreOffice / Word)
  render.py     # Markdown -> styled resume .docx
examples/       # Fictional resume and job posting for trying it out
tests/
```

## Roadmap (ideas)

- [x] Phase 1: tailor resume to a job posting (MD / DOCX / PDF)
- [ ] Cover letter generation in your own voice
- [ ] Job search and ranking from job boards (e.g. through an MCP server)
- [ ] Application tracker (which jobs you applied to, with which resume version)
- [ ] Answers to common application questions, saved and reused
- [ ] Human-in-the-loop form filling. You always review and click "Submit" yourself, since
      many job sites forbid automated submissions.
