"""Wrapper around LLM providers for cover letter generation."""
from __future__ import annotations

from typing import Iterable

from openai import OpenAI

try:  # pragma: no cover - optional dependency
    from together import Together
except ImportError:  # pragma: no cover - handled at runtime
    Together = None  # type: ignore[assignment]


class LLMClient:
    """Thin wrapper that hides provider-specific client details."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        temperature: float,
        openai_api_key: str | None = None,
        together_api_key: str | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._temperature = temperature

        if provider == "openai":
            if openai_api_key is None:
                raise ValueError("openai_api_key must be provided for provider='openai'")
            self._client = OpenAI(api_key=openai_api_key)
        elif provider == "together":
            if together_api_key is None:
                raise ValueError("together_api_key must be provided for provider='together'")
            if Together is None:
                raise RuntimeError(
                    "The 'together' package is required for provider='together'. Install the extra dependency."
                )
            self._client = Together(api_key=together_api_key)
        else:  # pragma: no cover - defensive
            raise ValueError(f"Unsupported provider: {provider}")

    def generate(self, messages: Iterable[dict[str, str]]) -> str:
        payload = list(messages)
        if not payload:
            raise ValueError("At least one message is required to call the LLM")

        if self._provider == "openai":
            response = self._client.chat.completions.create(  # type: ignore[attr-defined]
                model=self._model,
                messages=payload,
                temperature=self._temperature,
            )
        elif self._provider == "together":
            response = self._client.chat.completions.create(  # type: ignore[attr-defined]
                model=self._model,
                messages=payload,
                temperature=self._temperature,
            )
        else:  # pragma: no cover - defensive
            raise ValueError(f"Unsupported provider: {self._provider}")

        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError("LLM response contained no choices")

        message = choices[0].message
        if isinstance(message, dict):
            return message.get("content", "")
        return getattr(message, "content", "")
