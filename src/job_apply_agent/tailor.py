"""Resume tailoring agent built on the Claude Agent SDK.

The Agent SDK runs the Claude Code engine, so it authenticates the same way Claude Code
does on your machine: with your Claude subscription login (``claude`` -> /login, or a
``CLAUDE_CODE_OAUTH_TOKEN`` from ``claude setup-token``), or with ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from .prompts import (
    JOB_TEXT_SECTION,
    JOB_URL_SECTION,
    TAILOR_OUTPUT_SCHEMA,
    TAILOR_SYSTEM_PROMPT,
    TAILOR_USER_PROMPT,
)

ProgressFn = Callable[[str], None]


class TailoringError(RuntimeError):
    """Raised when the agent does not return a usable tailored resume."""


@dataclass
class TailoredResume:
    job_title: str
    company: str
    tailored_resume_markdown: str
    match_score: int
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    questions_for_candidate: list[str] = field(default_factory=list)
    notes: str = ""
    cost_usd: float | None = None  # Reported by the SDK; with a subscription you are not billed per token.

    @classmethod
    def from_structured_output(cls, data: dict[str, Any], cost_usd: float | None = None) -> TailoredResume:
        return cls(
            job_title=str(data.get("job_title", "")),
            company=str(data.get("company", "")),
            tailored_resume_markdown=str(data.get("tailored_resume_markdown", "")).strip(),
            match_score=int(data.get("match_score", 0)),
            matched_keywords=list(data.get("matched_keywords", [])),
            missing_keywords=list(data.get("missing_keywords", [])),
            changes=list(data.get("changes", [])),
            questions_for_candidate=list(data.get("questions_for_candidate", [])),
            notes=str(data.get("notes", "")),
            cost_usd=cost_usd,
        )

    def report_markdown(self) -> str:
        """A human-readable report to save next to the resume."""

        def bullets(items: list[str]) -> str:
            return "\n".join(f"- {item}" for item in items) if items else "- (none)"

        target = self.job_title + (f" at {self.company}" if self.company else "")
        return (
            f"# Tailoring report: {target}\n\n"
            f"**Estimated match:** {self.match_score}/100\n\n"
            f"## Matched requirements\n{bullets(self.matched_keywords)}\n\n"
            f"## Requirements your resume doesn't show (not added)\n{bullets(self.missing_keywords)}\n\n"
            f"## Changes made\n{bullets(self.changes)}\n\n"
            f"## Questions for you\n"
            f"Answering these (and adding true answers to your master resume) can improve the result:\n"
            f"{bullets(self.questions_for_candidate)}\n\n"
            f"## Notes\n{self.notes or '(none)'}\n"
        )


def build_options(*, use_web_fetch: bool, model: str | None = None) -> ClaudeAgentOptions:
    """Agent configuration: a locked-down agent whose only possible tool is WebFetch."""
    tools = ["WebFetch"] if use_web_fetch else []
    return ClaudeAgentOptions(
        system_prompt=TAILOR_SYSTEM_PROMPT,
        tools=tools,  # The only tools Claude can see.
        allowed_tools=tools,  # Auto-approve them...
        permission_mode="dontAsk",  # ...and deny anything else without prompting.
        setting_sources=[],  # Don't load your personal ~/.claude settings or CLAUDE.md files.
        output_format={"type": "json_schema", "schema": TAILOR_OUTPUT_SCHEMA},
        max_turns=8,
        model=model,  # None = your account's default model in Claude Code.
    )


def build_prompt(
    resume_markdown: str,
    *,
    job_text: str | None = None,
    job_url: str | None = None,
    extra_instructions: str | None = None,
) -> str:
    if bool(job_text) == bool(job_url):
        raise ValueError("Provide exactly one of job_text or job_url.")
    job_section = (
        JOB_TEXT_SECTION.format(job_text=job_text.strip())
        if job_text
        else JOB_URL_SECTION.format(job_url=job_url)
    )
    extra = f"Additional instructions from me:\n{extra_instructions.strip()}\n\n" if extra_instructions else ""
    return TAILOR_USER_PROMPT.format(
        resume=resume_markdown.strip(), job_section=job_section, extra_instructions=extra
    )


async def tailor_resume(
    resume_markdown: str,
    *,
    job_text: str | None = None,
    job_url: str | None = None,
    extra_instructions: str | None = None,
    model: str | None = None,
    on_progress: ProgressFn | None = None,
) -> TailoredResume:
    """Ask Claude to tailor ``resume_markdown`` to a job posting (given as text or URL)."""
    if not resume_markdown.strip():
        raise ValueError("The resume is empty.")

    prompt = build_prompt(
        resume_markdown, job_text=job_text, job_url=job_url, extra_instructions=extra_instructions
    )
    options = build_options(use_web_fetch=job_url is not None, model=model)
    progress = on_progress or (lambda _msg: None)

    result: ResultMessage | None = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    progress(f"Using tool: {block.name}")
                elif isinstance(block, TextBlock) and block.text.strip():
                    progress(block.text.strip())
        elif isinstance(message, ResultMessage):
            result = message

    if result is None:
        raise TailoringError("The agent finished without returning a result.")
    if result.is_error or result.subtype != "success":
        details = "; ".join(result.errors or []) or result.result or result.stop_reason or "unknown error"
        raise TailoringError(f"The agent failed ({result.subtype}): {details}")
    if not isinstance(result.structured_output, dict):
        raise TailoringError("The agent did not return structured output.")

    tailored = TailoredResume.from_structured_output(result.structured_output, cost_usd=result.total_cost_usd)
    if not tailored.tailored_resume_markdown:
        raise TailoringError(f"No resume was produced. Agent notes: {tailored.notes or '(none)'}")
    return tailored


def auth_warning() -> str | None:
    """Warn when an API key would override the subscription login (and bill API credits)."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return (
            "ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN is set, so the agent will use (and bill) that API "
            "credential instead of your Claude subscription. Unset it to use your subscription."
        )
    return None
