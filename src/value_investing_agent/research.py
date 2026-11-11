"""One-shot ADK execution and lossless grounding metadata capture."""

import asyncio
import logging
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types

from .agent import create_agent
from .config import DEFAULT_RESEARCH_TIMEOUT, Settings, require_credentials

logger = logging.getLogger(__name__)


class ResearchError(RuntimeError):
    """Research could not produce a usable, search-grounded response."""


class ResearchTimeoutError(TimeoutError):
    """A research timeout with a credential-free, user-facing explanation."""


@dataclass(frozen=True)
class ResearchResult:
    query: str
    model: str
    retrieved_at_utc: str
    report: str
    grounding_metadata: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sources(self) -> list[dict[str, str]]:
        sources = {}
        for metadata in self.grounding_metadata:
            for chunk in metadata.get("grounding_chunks", []):
                web = chunk.get("web") or {}
                uri = web.get("uri", "")
                if uri.startswith(("https://", "http://")):
                    sources.setdefault(uri, {"title": web.get("title") or uri, "uri": uri})
        return list(sources.values())

    @property
    def search_suggestions(self) -> list[str]:
        return list(
            dict.fromkeys(
                entry["search_entry_point"]["rendered_content"]
                for entry in self.grounding_metadata
                if entry.get("search_entry_point", {}).get("rendered_content")
            )
        )


async def analyze(
    query: str, *, timeout: float = DEFAULT_RESEARCH_TIMEOUT, settings: Settings | None = None
) -> ResearchResult:
    if not query.strip():
        raise ValueError("Provide a ticker, company, or research question.")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite positive number.")
    settings = settings or Settings.from_env()
    require_credentials()
    metadata = []
    final_text = ""
    deadline = asyncio.timeout(timeout)
    phase = "starting the research session"
    event_count = 0
    # The context manager closes the model clients and runner on success/failure.
    try:
        async with InMemoryRunner(agent=create_agent(settings)) as runner, deadline:
            session = await runner.session_service.create_session(
                app_name=runner.app_name,
                user_id="local_user",
                session_id=uuid4().hex,
            )
            phase = "waiting for Gemini's search-grounded report"
            async for event in runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=types.Content(role="user", parts=[types.Part(text=query.strip())]),
                run_config=RunConfig(max_llm_calls=12),
            ):
                event_count += 1
                phase = "waiting for Gemini to finish the report"
                if event.error_code:
                    raise ResearchError(f"Gemini request failed ({event.error_code}).")
                if event.grounding_metadata:
                    metadata.append(
                        event.grounding_metadata.model_dump(mode="json", exclude_none=True)
                    )
                if event.is_final_response() and event.content:
                    final_text = "\n".join(
                        part.text
                        for part in (event.content.parts or [])
                        if part.text and not part.thought
                    ).strip()
    except TimeoutError:
        # Never log the raw SDK exception, which can contain credentials or URLs.
        logger.warning(
            "Research timeout: model=%s limit_seconds=%s deadline_expired=%s phase=%s events=%s",
            settings.model, timeout, deadline.expired(), phase, event_count,
        )
        if deadline.expired():
            suggestion = (
                "Select a longer research time limit or ask a narrower question."
                if timeout < 600 else "Ask a narrower question or try again later."
            )
            message = f"Research timed out after {timeout:g} seconds while {phase}. {suggestion}"
        else:
            message = (
                "The Gemini request timed out before the research time limit. "
                "Try again or check your network connection and Gemini service availability."
            )
        raise ResearchTimeoutError(message) from None
    if not final_text:
        raise ResearchError("Gemini returned no report. Try a more specific research question.")
    result = ResearchResult(
        query=query.strip(),
        model=settings.model,
        retrieved_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        report=final_text,
        grounding_metadata=metadata,
    )
    if not result.sources:
        raise ResearchError(
            "Gemini returned no Google Search sources; the report was withheld. "
            "Try a specific stock and verify that your Gemini model supports Google Search grounding."
        )
    return result
