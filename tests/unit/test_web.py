"""Exercise the browser/server boundary without using Gemini API quota."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from value_investing_agent.config import ConfigurationError
from value_investing_agent.research import ResearchError, ResearchResult, ResearchTimeoutError
from value_investing_agent.web import app, main


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def result():
    return ResearchResult(
        query="Analyze AAPL",
        model="gemini-test",
        retrieved_at_utc="2026-11-11T12:00:00+00:00",
        report="Research <script>alert('unsafe')</script>",
        grounding_metadata=[
            {
                "grounding_chunks": [
                    {"web": {"title": "Filing", "uri": "https://example.com/filing"}}
                ],
                "search_entry_point": {"rendered_content": "<div>Google suggestions</div>"},
            }
        ],
    )


def test_web_page_and_local_assets_are_served_without_credentials(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="research-form"' in response.text
    assert 'sandbox="allow-popups allow-popups-to-escape-sandbox"' in response.text
    for path in ("/static/styles.css", "/static/app.js"):
        assert client.get(path).status_code == 200


def test_web_research_preserves_sources_and_downloads(client, result):
    with patch("value_investing_agent.web.analyze", new=AsyncMock(return_value=result)) as run:
        response = client.post("/api/research", json={"query": "  Analyze AAPL  ", "timeout": 300})
    assert response.status_code == 200
    run.assert_awaited_once_with("Analyze AAPL", timeout=300)
    data = response.json()
    assert data["sources"] == result.sources
    assert data["grounding_metadata"] == result.grounding_metadata
    assert json.loads(data["exports"]["json"]) == result.to_dict()
    assert "https://example.com/filing" in data["exports"]["md"]
    assert "<script>alert" not in data["exports"]["html"]
    assert "&lt;script&gt;" in data["exports"]["html"]
    assert "<div>Google suggestions</div>" in data["exports"]["html"]


def test_web_default_allows_five_minutes(client, result):
    with patch("value_investing_agent.web.analyze", new=AsyncMock(return_value=result)) as run:
        response = client.post("/api/research", json={"query": "AAPL"})
    assert response.status_code == 200
    run.assert_awaited_once_with("AAPL", timeout=300)
    assert '<option value="300" selected>' in client.get("/").text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"query": ""},
        {"query": "   "},
        {"query": "A" * 4001},
        {"query": "AAPL", "timeout": 0},
        {"query": "AAPL", "timeout": 601},
        {"query": "AAPL", "timeout": "nan"},
        {"query": "AAPL", "timeout": "inf"},
    ],
)
def test_invalid_web_requests_do_not_start_research(client, payload):
    with patch("value_investing_agent.web.analyze", new=AsyncMock()) as run:
        assert client.post("/api/research", json=payload).status_code == 422
    run.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "status", "message"),
    [
        (TimeoutError(), 504, "timed out"),
        (TimeoutError("request?key=secret"), 504, "upstream request timed out"),
        (ResearchTimeoutError("Research timed out after 300 seconds."), 504, "300 seconds"),
        (ConfigurationError("Set GOOGLE_API_KEY in .env."), 503, "GOOGLE_API_KEY"),
        (ResearchError("No Google Search sources."), 502, "Google Search sources"),
        (RuntimeError("request?key=secret"), 502, "API key"),
        (ValueError("request?key=secret"), 502, "API key"),
    ],
)
def test_web_errors_are_actionable_and_hide_sdk_secrets(client, error, status, message):
    with patch("value_investing_agent.web.analyze", new=AsyncMock(side_effect=error)):
        response = client.post("/api/research", json={"query": "AAPL"})
    assert response.status_code == status
    assert message in response.json()["detail"]
    assert "secret" not in response.text


def test_foreign_origin_cannot_start_paid_research(client):
    with patch("value_investing_agent.web.analyze", new=AsyncMock()) as run:
        response = client.post(
            "/api/research", json={"query": "AAPL"}, headers={"Origin": "https://foreign.test"}
        )
    assert response.status_code == 403
    run.assert_not_awaited()


def test_same_origin_can_start_research(client, result):
    with patch("value_investing_agent.web.analyze", new=AsyncMock(return_value=result)):
        response = client.post(
            "/api/research", json={"query": "AAPL"}, headers={"Origin": "http://testserver"}
        )
    assert response.status_code == 200


def test_request_without_json_content_type_cannot_start_research(client):
    with patch("value_investing_agent.web.analyze", new=AsyncMock()) as run:
        response = client.post("/api/research", content='{"query":"AAPL"}')
    # FastAPI versions may reject the body before the endpoint's media-type check.
    assert response.status_code in {415, 422}
    run.assert_not_awaited()


def test_default_command_starts_local_web_server(capsys):
    with patch("value_investing_agent.web.uvicorn.run") as serve:
        assert main([]) == 0
    serve.assert_called_once_with(app, host="127.0.0.1", port=8000)
    assert "http://127.0.0.1:8000" in capsys.readouterr().out


def test_server_can_use_another_local_port():
    with patch("value_investing_agent.web.uvicorn.run") as serve:
        assert main(["--port", "8080"]) == 0
    serve.assert_called_once_with(app, host="127.0.0.1", port=8080)


@pytest.mark.parametrize("port", ["0", "65536"])
def test_server_rejects_invalid_port(port):
    with patch("value_investing_agent.web.uvicorn.run") as serve, pytest.raises(SystemExit):
        main(["--port", port])
    serve.assert_not_called()
