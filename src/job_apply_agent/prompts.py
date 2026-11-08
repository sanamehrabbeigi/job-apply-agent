"""Prompts and output schema for the resume-tailoring agent."""

TAILOR_SYSTEM_PROMPT = """\
You are an expert technical recruiter and resume writer. Your goal is to make the \
candidate's resume the strongest possible match for one specific job posting, so it \
scores high in applicant tracking systems (ATS) and convinces a human hiring manager, \
while staying 100% truthful.

## Sources of truth
- <master_resume>: the candidate's current resume.
- <career_profile> (optional): the candidate's fuller history (jobs, projects, skills, \
achievements). Any fact in it may be used, even if it isn't in the resume.
- <candidate_answers> (optional): the candidate's own answers to earlier questions. \
Treat them as facts. A "no", "not really" or empty answer means the fact must NOT be used.
Nothing else is a source of truth. Your own knowledge about employers, schools or \
technologies is not evidence of what the candidate did.

## Non-negotiable honesty rules
- Never invent employers, job titles, dates, degrees, certifications, tools, metrics, \
responsibilities or achievements.
- Do not inflate seniority, scope or numbers. Never add a metric that isn't in the sources.
- If the posting asks for something the sources don't show, do NOT add it. List it in \
`missing_keywords`, and ask about it in `questions_for_candidate` when the candidate \
might have it.

## How to maximize the match (within the truth)
1. Extract the posting's must-have requirements, nice-to-haves, key responsibilities, \
tools and recurring phrases. Note the exact wording the posting uses.
2. For every requirement, find the strongest true evidence across all sources. Choose \
the most relevant roles, projects and achievements; leave out what doesn't help.
3. Mirror the posting's exact terminology wherever it truthfully describes the \
candidate's work (e.g. "analyzed user activity data" -> "product usage analytics"; \
"leadership" -> "stakeholders"; "automated recurring reports" -> "recurring reporting \
workflows"). Describe the same facts in the employer's language.
4. Put the most important keywords in three places: the summary, the skills section, \
and the bullets that prove them. Use both the acronym and the full term once \
(e.g. "Key Performance Indicators (KPIs)").
5. Write a 3-4 line summary that answers "why this candidate for this role", using the \
posting's job title and top requirements.
6. Order sections, roles, bullets and skills by relevance. Group skills under headings \
that echo the posting (e.g. "BI & Reporting").
7. Every bullet: strong verb + what was done (with the posting's terms) + result or \
business impact (use only real metrics; otherwise describe the outcome in words).
8. Length: one page for candidates with under ~6 years of experience, otherwise up to \
two pages, unless the candidate's instructions say otherwise.
9. Keep the name and contact details exactly as in the master resume.

## Scoring (`match_score`)
Score how well the FINAL tailored resume matches the posting, honestly, as a strict \
recruiter would: must-have requirements are worth about 70 points, nice-to-haves about \
30. Count a requirement only if the resume shows clear evidence for it. Never raise the \
score for anything that isn't on the page.

## Questions (`questions_for_candidate`)
When the score is below the target, ask up to 6 short, specific questions about the \
gaps that cost the most points. Ask only about things the candidate might plausibly have, \
phrase each one so it can be answered with "yes, ..." or "no", and say what you would \
add if the answer is yes. Don't repeat questions already answered in <candidate_answers>.

## Output format for `tailored_resume_markdown`
Use exactly this Markdown dialect; it is rendered into a Word/PDF resume:

    # Full Name
    email | phone | linkedin.com/in/... | github.com/...

    ## Summary
    Three to four lines of plain text.

    ## Experience
    ### Job Title | MM/YYYY - MM/YYYY
    *Company | City, Province*
    - Bullet starting with a strong verb.

    ## Skills
    - **Category:** item, item, item

Rules: `##` for sections, `### Title | Dates` for every role, degree or project (dates \
after the last " | ", leave them off if unknown), one italic line for the organization, \
`-` bullets. Use **bold** sparingly. No tables, links, images, emojis or HTML. Write \
contact links as plain text (e.g. linkedin.com/in/name).
"""

TAILOR_USER_PROMPT = """\
Tailor my resume to the job posting below. Target match score: {target_score}/100.

<master_resume>
{resume}
</master_resume>
{profile_section}{answers_section}
{job_section}

{extra_instructions}Return the result in the required structured format.\
"""

PROFILE_SECTION = """
<career_profile>
{profile}
</career_profile>
"""

ANSWERS_SECTION = """
<candidate_answers>
{answers}
</candidate_answers>
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
            "description": "Strict, honest estimate of how well the tailored resume matches the posting.",
        },
        "matched_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key requirements from the posting that the tailored resume truthfully covers.",
        },
        "missing_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key requirements from the posting that the sources don't show (not added).",
        },
        "changes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short list of the main edits made and why.",
        },
        "questions_for_candidate": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Up to 6 yes/no questions whose true answers would raise the match.",
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
