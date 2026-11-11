"""Local configuration. Environment variables take precedence over .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_RESEARCH_TIMEOUT = 300


class ConfigurationError(ValueError):
    """A configuration error whose message is safe to display."""


@dataclass(frozen=True)
class Settings:
    model: str = "gemini-flash-latest"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(Path.cwd() / ".env", override=False)
        model = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
        if not model.startswith("gemini-"):
            raise ConfigurationError(
                "GEMINI_MODEL must be a Gemini model ID, such as gemini-flash-latest."
            )
        return cls(model=model)


def require_credentials() -> None:
    """Fail before starting a paid request if no API key was configured."""
    if not (os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()):
        raise ConfigurationError(
            "Set GOOGLE_API_KEY in your environment or .env file before running research."
        )
