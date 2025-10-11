"""Utilities to extract job descriptions from URLs or local files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/119.0 Safari/537.36"
)


class JobDescriptionError(RuntimeError):
    """Raised when a job description cannot be retrieved or parsed."""


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fetch_job_description(source: str, *, timeout: int = 20) -> str:
    """Load a job description from a URL or local path.

    Args:
        source: HTTP(s) URL or filesystem path to a text/HTML document.
        timeout: Timeout for HTTP requests in seconds.

    Returns:
        Cleaned text content of the job description.
    """

    if source.startswith("http://") or source.startswith("https://"):
        response = requests.get(source, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
        if response.status_code >= 400:
            raise JobDescriptionError(
                f"Request to {source} failed with status {response.status_code}."
            )
        return _html_to_text(response.text)

    path = Path(source)
    if not path.exists():
        raise JobDescriptionError(f"Job description source not found: {source}")

    text = path.read_text(encoding="utf-8")
    if "<html" in text.lower():
        return _html_to_text(text)
    return _normalize_whitespace(text)


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.find_all(["script", "style", "noscript"]):
        element.extract()
    text = soup.get_text(separator=" ")
    return _normalize_whitespace(text)
