"""High-level orchestration of the cover letter generation workflow."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

from .config import settings
from .cv_loader import CVLoader
from .job_fetcher import fetch_job_description
from .latex import LetterLayout, Recipient, Sender, compile_pdf, render_letter, write_latex
from .llm import LLMClient
from .prompting import PromptContext, build_prompt


@dataclass
class PipelineResult:
    job_description_path: Path
    tex_path: Path
    pdf_path: Path | None
    raw_letter_body: str


@dataclass
class RecipientConfig:
    company: str | None = None
    name: str | None = None
    address: Sequence[str] = field(default_factory=list)


@dataclass
class SenderConfig:
    name: str
    address: Sequence[str] = field(default_factory=list)


@dataclass
class PipelineConfig:
    job_source: str
    recipient: RecipientConfig
    sender: SenderConfig
    opening: str = "Dear Hiring Manager"
    closing: str = "Sincerely,"
    output_stem: str | None = None
    role: str | None = None
    company: str | None = None
    tone: str = "professional"
    additional_instructions: str | None = None
    compile_pdf: bool = True


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """Run the full job description -> PDF pipeline."""

    job_description = fetch_job_description(config.job_source)
    cv_text = CVLoader(settings.cv_path).load()

    recipient_company = _derive_recipient_company(
        job_source=config.job_source,
        job_description=job_description,
        explicit_company=config.company,
        recipient_company_hint=config.recipient.company,
    )

    context_company = config.company or recipient_company

    context = PromptContext(
        role=config.role,
        company=context_company,
        tone=config.tone,
        additional_instructions=config.additional_instructions,
    )
    messages = build_prompt(cv_text=cv_text, job_description=job_description, context=context)

    client = LLMClient(
        provider=settings.llm_provider,
        model=settings.llm_model,
        temperature=settings.temperature,
        openai_api_key=settings.openai_api_key,
        together_api_key=settings.together_api_key,
    )
    raw_letter_body = client.generate(messages)
    letter_body = _sanitize_letter_body(
        raw_letter_body,
        opening=config.opening,
        closing=config.closing,
        sender_name=config.sender.name,
    )

    recipient_name = config.recipient.name or _derive_recipient_name(
        job_source=config.job_source,
        job_description=job_description,
        company_hint=context_company,
    )

    layout = LetterLayout(
        sender=Sender(name=config.sender.name, address=config.sender.address),
        recipient=Recipient(
            name=recipient_name,
            company=recipient_company,
            address=config.recipient.address,
        ),
        opening=config.opening,
        closing=config.closing,
        letter_body=letter_body,
    )

    latex_source = render_letter(settings.latex_template, layout)

    output_stem = config.output_stem or _default_stem(config, recipient_company)
    tex_path = write_latex(settings.output_dir, output_stem, latex_source)

    pdf_path = compile_pdf(tex_path, settings.latex_engine) if config.compile_pdf else None

    # Persist job description snapshot for traceability
    job_desc_path = tex_path.with_suffix(".job.txt")
    job_desc_path.write_text(job_description, encoding="utf-8")

    return PipelineResult(
        job_description_path=job_desc_path,
        tex_path=tex_path,
        pdf_path=pdf_path,
        raw_letter_body=letter_body,
    )


def _default_stem(config: PipelineConfig, recipient_company: str) -> str:
    today = date.today().isoformat()
    parts = [_slugify_segment(recipient_company or "company", fallback="company"), today]
    if config.role:
        parts.insert(0, _slugify_segment(config.role, fallback="role"))
    return "-".join(parts)


_CONTACT_PATTERNS = [
    r"contact\s+(?:name\s*)?[:\-]\s*(?P<name>[A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,2})",
    r"hiring manager\s*[:\-]\s*(?P<name>[A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,2})",
    r"recruiter\s*[:\-]\s*(?P<name>[A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,2})",
]
_GENERIC_SUBDOMAINS = {"www", "jobs", "careers", "apply", "work", "job", "careersite"}


def _derive_recipient_name(*, job_source: str, job_description: str, company_hint: str | None) -> str:
    """Best-effort derivation of a recipient name from source metadata."""

    contact = _extract_contact_name(job_description)
    if contact:
        return contact

    company = company_hint or _domain_to_company(job_source)
    if company:
        return f"{company} Hiring Team"

    return "Hiring Manager"


def _extract_contact_name(job_description: str) -> str | None:
    for pattern in _CONTACT_PATTERNS:
        match = re.search(pattern, job_description, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group("name").strip()
        normalized = _normalize_person_name(raw)
        if normalized:
            return normalized
    return None


def _normalize_person_name(value: str) -> str | None:
    tokens: list[str] = []
    for token in re.split(r"\s+", value):
        cleaned = re.sub(r"[^A-Za-z'\-]", "", token)
        if not cleaned:
            continue
        tokens.append(cleaned.capitalize())
    return " ".join(tokens) if tokens else None


def _derive_recipient_company(
    *,
    job_source: str,
    job_description: str,
    explicit_company: str | None,
    recipient_company_hint: str | None,
) -> str:
    for candidate in (explicit_company, recipient_company_hint, _extract_company_name(job_description), _domain_to_company(job_source)):
        normalized = _normalize_company_name(candidate)
        if normalized:
            return normalized
    return "Company"


def _domain_to_company(job_source: str) -> str | None:
    parsed = urlparse(job_source)
    host = parsed.netloc
    if not host:
        return None

    host = host.split("@").pop()  # strip credentials if present
    host = host.split(":")[0]
    parts = [segment for segment in host.split(".") if segment]
    if not parts:
        return None

    for segment in parts:
        lowered = segment.lower()
        if lowered not in _GENERIC_SUBDOMAINS:
            candidate = segment
            break
    else:
        candidate = parts[0]

    candidate = candidate.replace("-", " ").replace("_", " ")
    candidate = re.sub(r"[^A-Za-z0-9 '\-]", " ", candidate)
    formatted = " ".join(word.capitalize() for word in candidate.split())
    return formatted or None


_COMPANY_PATTERNS = [
    r"(?im)^\s*(?:company|employer)(?:\s+name)?\s*[:\-]\s*(?P<company>[A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,4})",
    r"join\s+the\s+(?P<company>[A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,4})\s+team",
]


def _extract_company_name(job_description: str) -> str | None:
    for pattern in _COMPANY_PATTERNS:
        match = re.search(pattern, job_description, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group("company").strip()
        normalized = _normalize_company_name(raw)
        if normalized:
            return normalized
    return None


def _normalize_company_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9 &'\-]", " ", value)
    words = [word.capitalize() for word in cleaned.split() if word.strip()]
    return " ".join(words) if words else None


def _slugify_segment(value: str, *, fallback: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"\s+", "-", lowered)
    slug = re.sub(r"[^a-z0-9\-]", "", lowered)
    return slug or fallback


def _sanitize_letter_body(value: str, *, opening: str, closing: str, sender_name: str) -> str:
    """Remove duplicated structural elements left by the LLM response."""

    if not value:
        return ""

    cleaned = value

    # Drop explicit LaTeX structural commands we handle in the template
    cleaned = re.sub(
        r"\\(opening|closing|signature|address|date)\s*\{[^{}]*\}",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\\(begin|end)\{letter\}", "", cleaned, flags=re.IGNORECASE)

    lines = [line.rstrip() for line in cleaned.strip().splitlines()]

    def _matches_phrase(text: str, phrase: str) -> bool:
        normalized_text = re.sub(r"[,\s]+$", "", text.strip().lower())
        normalized_phrase = re.sub(r"[,\s]+$", "", phrase.strip().lower())
        return bool(normalized_text) and normalized_text == normalized_phrase

    # Remove leading greeting if it matches the configured opening
    if lines and _matches_phrase(lines[0], opening):
        lines.pop(0)

    # Trim trailing closing/signature lines that mirror configured values
    while lines and (_matches_phrase(lines[-1], sender_name) or _matches_phrase(lines[-1], closing)):
        lines.pop()

    cleaned = "\n".join(line for line in lines if line.strip())
    return cleaned.strip()
