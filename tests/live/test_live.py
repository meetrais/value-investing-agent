"""Opt-in end-to-end check. Never spends API quota in the default test suite."""

import asyncio
import os

import pytest

from value_investing_agent.research import analyze


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_TESTS") != "1", reason="Set RUN_LIVE_TESTS=1 to use API quota"
)
def test_gemini_search_grounding():
    result = asyncio.run(
        analyze(
            "Use Google Search to find the latest available NASDAQ:AAPL stock price. "
            "Give the quote currency, source URL, and the quote's own timestamp. "
            "Keep this answer under 200 words.",
        )
    )
    assert result.report.strip()
    assert result.sources
    assert result.grounding_metadata
