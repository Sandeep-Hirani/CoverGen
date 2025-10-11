"""Load CV content from disk."""
from __future__ import annotations

from pathlib import Path


class CVLoader:
    """Utility to load CV text from a configurable path."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> str:
        if not self.path.exists():
            raise FileNotFoundError(
                f"CV file not found at {self.path}. Update your settings or create the file."
            )
        return self.path.read_text(encoding="utf-8").strip()
