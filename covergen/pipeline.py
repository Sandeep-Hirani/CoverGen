"""High-level orchestration of the cover letter generation workflow."""
from __future__ import annotations

import re
from collections import Counter
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
        role_hint=config.role,
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
        model=settings.model_for_provider(settings.llm_provider),
        temperature=settings.temperature,
        openai_api_key=settings.openai_api_key,
        together_api_key=settings.together_api_key,
        openrouter_api_key=settings.openrouter_api_key,
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
    role_hint: str | None,
) -> str:
    for candidate in (
        explicit_company,
        recipient_company_hint,
        _extract_company_name(job_description, role_hint),
        _domain_to_company(job_source),
    ):
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
    r"job\s+application\s+for\s+[A-Za-z0-9&'\/\-\s]{0,80}?\s+at\s+(?P<company>[A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,5})",
    r"(?:role|opening|position)\s+(?:at|with)\s+(?P<company>[A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,4})",
]

_COMPANY_TRAILING_STOPWORDS = {
    "apply",
    "application",
    "associate",
    "careers",
    "career",
    "contract",
    "department",
    "developer",
    "development",
    "engineer",
    "engineering",
    "group",
    "hiring",
    "hybrid",
    "intern",
    "internship",
    "job",
    "jobs",
    "lead",
    "manager",
    "managers",
    "opening",
    "opportunity",
    "position",
    "product",
    "remote",
    "role",
    "software",
    "team",
    "teams",
    "time",
    "united",
    "states",
    "usa",
    "washington",
    "seattle",
    "san",
    "francisco",
    "new",
    "york",
    "california",
    "austin",
    "texas",
    "boston",
    "canada",
    "toronto",
    "london",
    "europe",
    "global",
    "worldwide",
    "north",
    "america",
    "contractor",
    "staff",
    "senior",
    "principal",
    "director",
    "specialist",
    "scientist",
    "analyst",
    "consultant",
    "coach",
    "fellow",
    "assistant",
    "support",
    "customer",
    "success",
    "solutions",
    "operations",
    "operations",
    "sales",
    "marketing",
    "service",
}

_COMPANY_ALLOWED_SUFFIXES = {
    "inc",
    "inc.",
    "llc",
    "l.l.c.",
    "ltd",
    "ltd.",
    "plc",
    "ag",
    "gmbh",
    "bv",
    "lp",
    "llp",
    "co",
    "co.",
    "corp",
    "corporation",
    "company",
}

_FREQUENCY_EXCLUSIONS = {
    "apply",
    "job",
    "application",
    "role",
    "position",
    "opening",
    "team",
    "teams",
    "department",
    "company",
    "employer",
    "opportunity",
    "career",
    "careers",
    "remote",
    "hybrid",
    "full",
    "time",
    "part",
    "contract",
    "united",
    "states",
    "state",
    "city",
    "jobs",
    "global",
    "worldwide",
    "country",
}


def _extract_company_name(job_description: str, role_hint: str | None) -> str | None:
    role_tokens = _tokenize_role(role_hint)
    for pattern in _COMPANY_PATTERNS:
        match = re.search(pattern, job_description, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group("company").strip()
        candidate = _sanitize_company_candidate(raw, role_tokens)
        normalized = _normalize_company_name(candidate)
        if normalized:
            return normalized

    fallback = _guess_company_by_frequency(job_description, role_tokens)
    if fallback:
        return fallback
    return None


def _normalize_company_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9 &'\-]", " ", value)
    words = [word.capitalize() for word in cleaned.split() if word.strip()]
    return " ".join(words) if words else None


def _sanitize_company_candidate(value: str, role_tokens: set[str]) -> str | None:
    tokens = [token for token in re.split(r"\s+", value) if token.strip()]
    cleaned_tokens: list[str] = []
    for token in tokens:
        cleaned = re.sub(r"[^A-Za-z0-9&'\-]", "", token)
        if cleaned:
            cleaned_tokens.append(cleaned)
    if not cleaned_tokens:
        return None

    result = list(cleaned_tokens)
    while len(result) > 1:
        last = result[-1]
        lowered = last.lower()
        if lowered in _COMPANY_ALLOWED_SUFFIXES:
            break
        if lowered in role_tokens or lowered in _COMPANY_TRAILING_STOPWORDS:
            result.pop()
            continue
        if len(last) <= 2 and lowered not in {"ai", "ml", "xr"}:
            result.pop()
            continue
        break

    if not result:
        result = cleaned_tokens
    return " ".join(result)


def _tokenize_role(role_hint: str | None) -> set[str]:
    if not role_hint:
        return set()
    tokens = re.split(r"[^A-Za-z0-9&'\-]+", role_hint)
    return {token.strip().lower() for token in tokens if token.strip()}


_COMPANY_CONNECTORS = {"of", "and", "the", "&"}


def _guess_company_by_frequency(job_description: str, role_tokens: set[str]) -> str | None:
    if not job_description:
        return None

    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&'\-]*", job_description)
    counts: Counter[str] = Counter()
    first_occurrence: dict[str, int] = {}
    for idx, token in enumerate(tokens):
        if not token:
            continue
        if not token[0].isupper():
            continue
        lowered = token.lower()
        if lowered in role_tokens or lowered in _COMPANY_TRAILING_STOPWORDS or lowered in _FREQUENCY_EXCLUSIONS:
            continue
        if len(lowered) <= 2 and lowered not in {"ai", "ml", "xr"}:
            continue
        counts[lowered] += 1
        if lowered not in first_occurrence:
            first_occurrence[lowered] = idx

    if not counts:
        return None

    best_lower, _ = counts.most_common(1)[0]
    start_idx = first_occurrence[best_lower]
    candidate_tokens = [tokens[start_idx]]

    next_idx = start_idx + 1
    while next_idx < len(tokens):
        token = tokens[next_idx]
        lowered = token.lower()
        if lowered in _COMPANY_CONNECTORS:
            candidate_tokens.append(token)
            next_idx += 1
            continue
        if not token[0].isupper():
            break
        if lowered in role_tokens or lowered in _COMPANY_TRAILING_STOPWORDS or lowered in _FREQUENCY_EXCLUSIONS:
            break
        if len(lowered) <= 2 and lowered not in {"ai", "ml", "xr"} and lowered not in _COMPANY_ALLOWED_SUFFIXES:
            break
        candidate_tokens.append(token)
        next_idx += 1

    candidate = " ".join(candidate_tokens)
    return _normalize_company_name(candidate)


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

    normalized_lines: list[str] = []
    blank_pending = False
    for line in lines:
        if not line.strip():
            blank_pending = True
            continue
        if blank_pending and normalized_lines:
            normalized_lines.append("")
            blank_pending = False
        normalized_lines.append(line)

    cleaned = "\n".join(normalized_lines).strip()

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", cleaned) if paragraph.strip()]
    if len(paragraphs) == 1:
        sentences = re.split(r"(?<=[.!?])\s+", paragraphs[0])
        if len(sentences) >= 2:
            midpoint = max(1, len(sentences) // 2)
            first = " ".join(sentences[:midpoint]).strip()
            second = " ".join(sentences[midpoint:]).strip()
            paragraphs = [part for part in (first, second) if part]

    if len(paragraphs) > 3:
        paragraphs = paragraphs[:3]
    cleaned = "\n\n".join(paragraphs)

    # Escape common stray special characters that break LaTeX when emitted raw
    cleaned = re.sub(r"(?<!\\)#", r"\\#", cleaned)

    return cleaned
