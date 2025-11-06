"""Prompt construction helpers for the cover letter generation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PromptContext:
    """Structured information about the job and preferences."""

    role: Optional[str] = None
    company: Optional[str] = None
    tone: str = "professional"
    additional_instructions: Optional[str] = None


_SYSTEM_PROMPT = (
    "You craft tailored cover letter bodies in LaTeX. Return only the paragraphs "
    "that belong between \\opening and \\closing – no greetings, signatures, "
    "addresses, dates, or other structural commands. The output must be valid "
    "LaTeX and must not invent employers, achievements, or company names."
)


def build_prompt(cv_text: str, job_description: str, context: PromptContext | None = None) -> list[dict[str, str]]:
    """Return a chat-style prompt for the LLM API."""

    context = context or PromptContext()
    user_parts = [
        "Write the LaTeX body of a tailored cover letter for this candidate. Follow these rules:",
        "1. Produce two or three well-proportioned paragraphs that will sit between \\opening and \\closing; do not emit those commands yourself.",
        "2. Ground every claim in the CV. Do not invent employers, roles, accomplishments, or technologies that are not present.",
        "3. Mirror the role expectations, tooling, and priorities from the job description with concrete connections to the candidate's experience.",
        "4. Use the confirmed role and company exactly as provided. If a company is not confirmed, refer to it generically as \"the company\" instead of guessing.",
        "5. Maintain a polished, formal tone that is confident and warm; avoid slang, clichés, or filler phrases.",
        "6. Highlight one or two quantified achievements that map directly to the employer's needs.",
        "7. Close with a forward-looking sentence that reinforces enthusiasm and invites next steps.",
        "8. Separate each paragraph with exactly one blank line so LaTeX renders distinct paragraphs.",
    ]

    if context.role:
        user_parts.append(f"\nConfirmed role: {context.role}")
    if context.company:
        user_parts.append(f"Confirmed company: {context.company}")
    if context.tone:
        user_parts.append(f"Desired tone: {context.tone}")
    if context.additional_instructions:
        user_parts.append(f"Additional instructions: {context.additional_instructions}")

    user_parts.extend(
        [
            "",
            "Candidate CV:",
            cv_text,
            "",
            "Job description:",
            job_description,
        ]
    )

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(user_parts)},
    ]
