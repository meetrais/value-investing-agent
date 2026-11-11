import asyncio
from typing import ClassVar
from unittest.mock import patch

import pytest
from google.adk.events import Event
from google.genai import types

from value_investing_agent.config import Settings
from value_investing_agent.research import ResearchError, ResearchTimeoutError, analyze


def grounded_event(*, final=True):
    return Event(
        author="value_investing_agent",
        content=types.Content(
            role="model",
            parts=[
                types.Part(text="Private reasoning", thought=True),
                types.Part(text="Evidence-based research."),
                types.Part(text="Quote may be delayed."),
            ],
        ),
        partial=not final,
        grounding_metadata=types.GroundingMetadata(
            web_search_queries=["NYSE BRK.B stock price"],
            grounding_chunks=[
                types.GroundingChunk(
                    web=types.GroundingChunkWeb(uri="https://example.com/quote", title="Quote"),
                )
            ],
            grounding_supports=[
                types.GroundingSupport(
                    segment=types.Segment(
                        start_index=0, end_index=24, text="Evidence-based research."
                    ),
                    grounding_chunk_indices=[0],
                )
            ],
            search_entry_point=types.SearchEntryPoint(
                rendered_content="<div>Google suggestions</div>"
            ),
        ),
    )


class FakeRunner:
    events: ClassVar[list] = []
    failure = None
    closed = False
    calls: ClassVar[list] = []
    app_name = "value_investing_agent"

    def __init__(self, *, agent):
        self.session_service = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        type(self).closed = True

    async def create_session(self, **kwargs):
        self.calls.append(kwargs)
        from types import SimpleNamespace

        return SimpleNamespace(id=kwargs["session_id"], user_id=kwargs["user_id"])

    async def run_async(self, **kwargs):
        if self.failure:
            raise self.failure
        for event in self.events:
            yield event


@pytest.fixture(autouse=True)
def runner(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-never-sent")
    FakeRunner.events = []
    FakeRunner.failure = None
    FakeRunner.closed = False
    FakeRunner.calls = []
    with patch("value_investing_agent.research.InMemoryRunner", FakeRunner):
        yield FakeRunner


def run(query="Analyze NYSE:BRK.B", **kwargs):
    return asyncio.run(analyze(query, settings=Settings(), **kwargs))


def test_preserves_grounding_and_all_visible_parts(runner):
    runner.events = [grounded_event()]
    result = run()
    assert result.report == "Evidence-based research.\nQuote may be delayed."
    assert result.sources == [{"title": "Quote", "uri": "https://example.com/quote"}]
    assert result.search_suggestions == ["<div>Google suggestions</div>"]
    assert result.to_dict()["grounding_metadata"][0]["grounding_supports"]
    assert runner.closed


def test_grounding_on_nonfinal_event_is_preserved(runner):
    runner.events = [
        grounded_event(final=False),
        Event(
            author="value_investing_agent",
            content=types.Content(role="model", parts=[types.Part(text="Final report")]),
        ),
    ]
    assert run().report == "Final report"


def test_ungrounded_report_is_withheld(runner):
    runner.events = [
        Event(
            author="value_investing_agent",
            content=types.Content(
                role="model",
                parts=[types.Part(text="Unverified price: 123")],
            ),
        )
    ]
    with pytest.raises(ResearchError, match="no Google Search sources"):
        run()
    assert runner.closed


def test_no_final_response_is_error(runner):
    runner.events = [grounded_event(final=False)]
    with pytest.raises(ResearchError, match="no report"):
        run()


def test_api_errors_fail_and_close_runner(runner):
    runner.events = [
        Event(
            author="value_investing_agent",
            error_code="RESOURCE_EXHAUSTED",
            error_message="sensitive request details",
        )
    ]
    with pytest.raises(ResearchError, match="RESOURCE_EXHAUSTED") as error:
        run()
    assert "sensitive" not in str(error.value)
    assert runner.closed


def test_timeout_closes_runner(runner):
    runner.failure = TimeoutError()
    with pytest.raises(TimeoutError):
        run()
    assert runner.closed


def test_upstream_timeout_is_distinct_and_hides_sdk_secrets(runner, caplog):
    runner.failure = TimeoutError("request?key=secret")
    with pytest.raises(ResearchTimeoutError, match="before the research time limit") as error:
        run(timeout=300)
    assert "secret" not in str(error.value)
    assert "secret" not in caplog.text
    assert "deadline_expired=False" in caplog.text
    assert runner.closed


@pytest.mark.parametrize("received_event", [False, True])
def test_real_deadline_cancels_wait_and_reports_progress(runner, monkeypatch, caplog, received_event):
    async def waiting_response(self, **kwargs):
        if received_event:
            yield grounded_event(final=False)
        await asyncio.Event().wait()

    monkeypatch.setattr(runner, "run_async", waiting_response)
    with pytest.raises(ResearchTimeoutError, match="after 0.01 seconds") as error:
        run(timeout=0.01)
    assert "longer research time limit" in str(error.value)
    expected_phase = "finish the report" if received_event else "search-grounded report"
    assert expected_phase in str(error.value)
    assert "deadline_expired=True" in caplog.text
    assert f"events={int(received_event)}" in caplog.text
    assert runner.closed


def test_requests_get_independent_sessions(runner):
    runner.events = [grounded_event()]
    run()
    run()
    assert runner.calls[0]["session_id"] != runner.calls[1]["session_id"]


@pytest.mark.parametrize("query,timeout", [(" ", 10), ("AAPL", 0), ("AAPL", -1)])
def test_invalid_request_does_not_start_runner(query, timeout, runner):
    with pytest.raises(ValueError):
        run(query, timeout=timeout)
    assert not runner.calls
