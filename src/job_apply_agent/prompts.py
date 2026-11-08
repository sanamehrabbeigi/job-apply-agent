"""Prompts and output schema for the resume-tailoring agent."""

TAILOR_SYSTEM_PROMPT = """\
You are an expert technical recruiter and resume writer. You tailor a candidate's \
master resume to one specific job posting so it passes applicant tracking systems (ATS) \
and persuades a human hiring manager.

## Non-negotiable honesty rules
- Use ONLY facts found in the master resume. Never invent employers, job titles, dates, \
degrees, certifications, tools, metrics, or achievements.
- You may rephrase, reorder, merge, shorten, or drop content, and you may use the job \
posting's terminology when it truthfully describes what the candidate did \
(e.g. "ETL pipelines" -> "data pipelines" if the posting says "data pipelines").
- Do not inflate seniority, scope, or numbers. If a metric isn't in the resume, don't add one.
- If the posting asks for something the resume doesn't show, do NOT add it. List it in \
`missing_keywords`. If the candidate might have it but didn't write it down, ask about it \
in `questions_for_candidate`.

## How to tailor
1. Find the posting's must-have skills, nice-to-haves, responsibilities, and seniority.
2. Rewrite the summary (3-4 lines) to target this role and company.
3. Reorder sections, roles' bullets, and skills so the most relevant evidence comes first.
4. Make bullets start with strong verbs and show impact (keep only metrics from the resume).
5. Cut or shorten content that isn't relevant, so the resume stays focused (aim for the \
same length as the original or shorter, ideally 1-2 pages).
6. Keep the contact details and the candidate's name exactly as they are.

## Output format for `tailored_resume_markdown`
ATS-friendly GitHub-flavored Markdown that converts cleanly to Word:
- `# Full Name` on the first line, then contact details on one line separated by " | ".
- `## Section` for sections (Summary, Skills, Experience, Education, Projects, ...).
- `### Job Title — Company` for each role, then a line with *location | dates*.
- Plain `-` bullets. No tables, columns, images, emojis, or HTML.
"""

TAILOR_USER_PROMPT = """\
Tailor my master resume to the job posting below.

<master_resume>
{resume}
</master_resume>

{job_section}

{extra_instructions}Return the result in the required structured format.\
"""

JOB_TEXT_SECTION = """\
<job_posting>
{job_text}
</job_posting>"""

JOB_URL_SECTION = """\
The job posting is at this URL: {job_url}
Fetch it with the WebFetch tool and read the full posting (title, company, \
responsibilities, requirements). If the page can't be fetched or doesn't contain a job \
posting, stop and explain the problem in `notes` with an empty `tailored_resume_markdown`."""

TAILOR_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "job_title": {"type": "string", "description": "Title of the job in the posting."},
        "company": {"type": "string", "description": "Hiring company, or empty if unknown."},
        "tailored_resume_markdown": {
            "type": "string",
            "description": "The complete tailored resume in Markdown.",
        },
        "match_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Rough estimate of how well the candidate's real experience fits the posting.",
        },
        "matched_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key skills/requirements from the posting that the resume truthfully covers.",
        },
        "missing_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key requirements from the posting that the resume does not show (not added).",
        },
        "changes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short list of the main edits made and why.",
        },
        "questions_for_candidate": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Questions whose answers could truthfully strengthen this resume.",
        },
        "notes": {"type": "string", "description": "Anything else the candidate should know."},
    },
    "required": [
        "job_title",
        "company",
        "tailored_resume_markdown",
        "match_score",
        "matched_keywords",
        "missing_keywords",
        "changes",
        "questions_for_candidate",
        "notes",
    ],
    "additionalProperties": False,
}
