"""Configuration loading for CoverGen."""
from __future__ import annotations

import json

from pathlib import Path
from typing import Iterable, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import DotEnvSettingsSource, EnvSettingsSource


class _LenientEnvSettingsSource(EnvSettingsSource):
    """Environment source that tolerates non-JSON list values."""

    def decode_complex_value(self, field_name, field, value):
        try:
            return super().decode_complex_value(field_name, field, value)
        except json.JSONDecodeError:
            return value


class _LenientDotEnvSettingsSource(DotEnvSettingsSource):
    """Dotenv source mirroring the lenient environment parsing."""

    def decode_complex_value(self, field_name, field, value):
        try:
            return super().decode_complex_value(field_name, field, value)
        except json.JSONDecodeError:
            return value


class Settings(BaseSettings):
    """Runtime configuration for the cover letter pipeline."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            _LenientEnvSettingsSource(settings_cls),
            _LenientDotEnvSettingsSource(settings_cls),
            file_secret_settings,
        )

    llm_provider: Literal["openai", "together", "openrouter"] = Field(
        default="openai",
        validation_alias=AliasChoices("LLM_PROVIDER", "llm_provider"),
        description="Which LLM backend to call (openai, together, or openrouter).",
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"),
    )
    together_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TOGETHER_API_KEY", "together_api_key"),
    )
    openrouter_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "openrouter_api_key"),
    )
    llm_model: str = Field(
        default="gpt-4-turbo",
        validation_alias=AliasChoices("LLM_MODEL", "OPENAI_MODEL", "llm_model"),
        description="Model identifier passed to the configured provider.",
    )
    temperature: float = Field(
        default=0.2,
        validation_alias=AliasChoices("LLM_TEMPERATURE", "temperature"),
        description="Sampling temperature for LLM completions.",
    )
    cv_path: Path = Field(
        default=Path("data/cv.txt"),
        validation_alias=AliasChoices("CV_PATH", "cv_path"),
        description="Filesystem path to raw CV text.",
    )
    latex_template: Path = Field(
        default=Path("templates/cover_letter.tex.j2"),
        validation_alias=AliasChoices("LATEX_TEMPLATE", "latex_template"),
        description="Jinja2 template used to render the LaTeX cover letter.",
    )
    latex_engine: str = Field(
        default="xelatex",
        validation_alias=AliasChoices("LATEX_ENGINE", "latex_engine"),
        description="LaTeX engine to compile the generated document.",
    )
    output_dir: Path = Field(
        default=Path("output"),
        validation_alias=AliasChoices("OUTPUT_DIR", "output_dir"),
        description="Directory where generated assets are stored.",
    )

    default_sender_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEFAULT_SENDER_NAME", "default_sender_name"),
        description="Default sender name used by the CLI when not provided.",
    )
    default_sender_address: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("DEFAULT_SENDER_ADDRESS", "default_sender_address"),
        description="Default sender address lines (pipe-separated in env).",
    )
    default_recipient_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEFAULT_RECIPIENT_NAME", "default_recipient_name"),
        description=(
            "Legacy recipient name override. The CLI now derives this automatically from "
            "the job description unless explicitly provided via --recipient-name."
        ),
    )
    default_recipient_company: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEFAULT_RECIPIENT_COMPANY", "default_recipient_company"),
        description=(
            "Legacy recipient company override. The CLI now derives this automatically "
            "from the job metadata unless explicitly provided via --recipient-company."
        ),
    )
    default_recipient_address: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("DEFAULT_RECIPIENT_ADDRESS", "default_recipient_address"),
        description="Default recipient address lines (pipe-separated in env).",
    )
    default_opening: str = Field(
        default="Dear Hiring Manager",
        validation_alias=AliasChoices("DEFAULT_OPENING", "default_opening"),
        description="Default opening salutation.",
    )
    default_closing: str = Field(
        default="Sincerely,",
        validation_alias=AliasChoices("DEFAULT_CLOSING", "default_closing"),
        description="Default closing phrase.",
    )
    default_tone: str = Field(
        default="professional",
        validation_alias=AliasChoices("DEFAULT_TONE", "default_tone"),
        description="Default tone value passed to the LLM.",
    )

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.lower()
        return value

    @field_validator("cv_path", "latex_template", "output_dir", mode="before")
    @classmethod
    def _expand_path(cls, value: str | Path | None) -> Path | None:
        if value is None:
            return value
        return Path(value).expanduser()

    @field_validator("default_sender_address", "default_recipient_address", mode="before")
    @classmethod
    def _parse_address_list(cls, value: str | Iterable[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = value.split("|")
        else:
            items = list(value)
        cleaned = [str(item).strip() for item in items if str(item).strip()]
        return cleaned

    @model_validator(mode="after")
    def _validate_keys(self) -> "Settings":
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when llm_provider is 'openai'.")
        if self.llm_provider == "together" and not self.together_api_key:
            raise ValueError("TOGETHER_API_KEY is required when llm_provider is 'together'.")
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required when llm_provider is 'openrouter'.")
        return self


settings = Settings()
