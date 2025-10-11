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
    "You craft tailored cover letter bodies in LaTeX. Return only the main "
    "paragraph content – no opening commands, closing blocks, signatures, "
    "addresses, dates, or document preamble. The text must be valid LaTeX."
)


def build_prompt(cv_text: str, job_description: str, context: PromptContext | None = None) -> list[dict[str, str]]:
    """Return a chat-style prompt for the LLM API."""

    context = context or PromptContext()
    user_parts = [
        "Produce a LaTeX cover letter body tailored to the job.",
        "Use the candidate CV:",
        cv_text,
        "",
        "Job description:",
        job_description,
    ]

    if context.role:
        user_parts.append(f"\nTarget role: {context.role}")
    if context.company:
        user_parts.append(f"\nCompany: {context.company}")
    if context.tone:
        user_parts.append(f"\nDesired tone: {context.tone}")
    if context.additional_instructions:
        user_parts.append(f"\nAdditional guidance: {context.additional_instructions}")

    user_parts.append(
        "\nStructure guidance: write two to three focused paragraphs that naturally "
        "follow a formal greeting and precede a closing, but do not output the "
        "\\opening, \\closing, signature lines, or contact details – those are "
        "handled elsewhere."
    )

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(user_parts)},
    ]
