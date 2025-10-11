"""Render LaTeX cover letters and compile them to PDF."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from jinja2 import Environment, FileSystemLoader


@dataclass
class Sender:
    name: str
    address: Sequence[str]


@dataclass
class Recipient:
    name: str
    company: str
    address: Sequence[str]


@dataclass
class LetterLayout:
    sender: Sender
    recipient: Recipient
    opening: str
    closing: str
    letter_body: str


def _environment(template_path: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(template_path.parent),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_letter(template_path: Path, layout: LetterLayout) -> str:
    template = _environment(template_path).get_template(template_path.name)
    return template.render(
        sender=layout.sender,
        recipient=layout.recipient,
        opening=layout.opening,
        closing=layout.closing,
        letter_body=layout.letter_body,
    )


def write_latex(output_dir: Path, stem: str, latex_source: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    tex_path = output_dir / f"{stem}.tex"
    tex_path.write_text(latex_source, encoding="utf-8")
    return tex_path


def compile_pdf(tex_path: Path, engine: str) -> Path:
    command = [
        engine,
        "-interaction=nonstopmode",
        tex_path.name,
    ]
    try:
        subprocess.run(
            command,
            cwd=tex_path.parent,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError as exc:  # pragma: no cover - system-specific
        raise RuntimeError(
            f"LaTeX engine '{engine}' not found. Install it or update settings."
        ) from exc
    except subprocess.CalledProcessError as exc:
        output = exc.stdout.decode("utf-8", errors="ignore") if exc.stdout else ""
        snippet = output[-2000:] if output else "<no output>"
        raise RuntimeError(
            "LaTeX compilation failed. Inspect the log output for details."
            f"\nCommand: {' '.join(command)}"
            f"\nOutput snippet:\n{snippet}"
        ) from exc

    pdf_path = tex_path.with_suffix(".pdf")
    if not pdf_path.exists():  # pragma: no cover - defensive
        raise RuntimeError("Expected PDF not created by LaTeX engine.")
    return pdf_path
