"""Command line interface for the CoverGen project."""
from __future__ import annotations

from typing import Optional

import typer

from .config import settings
from .pipeline import PipelineConfig, RecipientConfig, SenderConfig, run_pipeline

app = typer.Typer(help="Generate tailored cover letters from job descriptions.")


@app.command("generate")
def generate_command(
    job_source: str = typer.Argument(..., help="URL or path to the job description."),
    role: Optional[str] = typer.Option(None, help="Target job title."),
    company: Optional[str] = typer.Option(
        None, help="Override company name emphasised in the letter."
    ),
    tone: Optional[str] = typer.Option(
        None,
        help="Desired tone (defaults to configuration).",
    ),
    instructions: Optional[str] = typer.Option(
        None, help="Additional guidance for the model."
    ),
    sender_name: Optional[str] = typer.Option(
        None, help="Sender full name (defaults to configuration)."
    ),
    sender_address: Optional[list[str]] = typer.Option(
        None,
        help="Sender address lines. Repeat the flag for multiple lines.",
    ),
    recipient_name: Optional[str] = typer.Option(
        None, help="Recipient name (auto-derived when omitted)."
    ),
    recipient_company: Optional[str] = typer.Option(
        None, help="Recipient company (auto-derived when omitted)."
    ),
    recipient_address: Optional[list[str]] = typer.Option(
        None,
        help="Recipient address lines. Repeat the flag for multiple lines.",
    ),
    opening: Optional[str] = typer.Option(
        None, help="Opening salutation (defaults to configuration)."
    ),
    closing: Optional[str] = typer.Option(
        None, help="Closing phrase (defaults to configuration)."
    ),
    output_stem: Optional[str] = typer.Option(
        None, help="Filename stem for generated artifacts."
    ),
    skip_pdf: bool = typer.Option(
        False, help="Skip LaTeX compilation and only write the .tex file."
    ),
):
    """Generate a customised cover letter."""

    sender_name_value = sender_name or settings.default_sender_name
    recipient_company_value = (
        recipient_company or settings.default_recipient_company
    )

    missing_fields: list[str] = []
    if not sender_name_value:
        missing_fields.append("--sender-name or DEFAULT_SENDER_NAME")
    if missing_fields:
        typer.secho(
            "Missing required identity details. Provide the flags or set them in the configuration:",
            fg=typer.colors.RED,
        )
        for field in missing_fields:
            typer.echo(f"  - {field}")
        raise typer.Exit(code=2)

    sender_address_value = (
        list(sender_address)
        if sender_address
        else list(settings.default_sender_address)
    )
    recipient_address_value = (
        list(recipient_address)
        if recipient_address
        else list(settings.default_recipient_address)
    )

    tone_value = tone or settings.default_tone
    opening_value = opening or settings.default_opening
    closing_value = closing or settings.default_closing

    company_value = company or recipient_company_value

    sender_cfg = SenderConfig(
        name=sender_name_value,
        address=sender_address_value,
    )
    recipient_cfg = RecipientConfig(
        company=recipient_company_value,
        name=recipient_name,
        address=recipient_address_value,
    )

    pipeline_cfg = PipelineConfig(
        job_source=job_source,
        recipient=recipient_cfg,
        sender=sender_cfg,
        opening=opening_value,
        closing=closing_value,
        output_stem=output_stem,
        role=role,
        company=company_value,
        tone=tone_value,
        additional_instructions=instructions,
        compile_pdf=not skip_pdf,
    )

    try:
        result = run_pipeline(pipeline_cfg)
    except Exception as exc:  # pragma: no cover - CLI feedback
        typer.secho(f"Error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho("Cover letter generated successfully!", fg=typer.colors.GREEN)
    typer.echo(f"Job description saved to: {result.job_description_path}")
    typer.echo(f"LaTeX saved to: {result.tex_path}")
    if result.pdf_path:
        typer.echo(f"PDF saved to: {result.pdf_path}")
    else:
        typer.echo("PDF generation skipped (use --skip-pdf to disable compilation).")


@app.command("show-settings")
def show_settings() -> None:
    """Display effective configuration values."""

    data = {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "openai_model": settings.openai_model or "(fallback to llm_model)",
        "together_model": settings.together_model or "(fallback to llm_model)",
        "openrouter_model": settings.openrouter_model or "(fallback to llm_model)",
        "temperature": settings.temperature,
        "cv_path": settings.cv_path,
        "latex_template": settings.latex_template,
        "latex_engine": settings.latex_engine,
        "output_dir": settings.output_dir,
        "default_sender_name": settings.default_sender_name,
        "default_sender_address": settings.default_sender_address,
        "default_recipient_name": (
            settings.default_recipient_name or "(auto from job description)"
        ),
        "default_recipient_company": (
            settings.default_recipient_company or "(auto from job source)"
        ),
        "default_recipient_address": settings.default_recipient_address,
        "default_opening": settings.default_opening,
        "default_closing": settings.default_closing,
        "default_tone": settings.default_tone,
    }
    for key, value in data.items():
        typer.echo(f"{key}: {value}")


if __name__ == "__main__":  # pragma: no cover
    app()
