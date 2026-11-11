import json
from unittest.mock import AsyncMock, patch

import pytest
from google.adk.tools import google_search

from value_investing_agent.agent import create_agent
from value_investing_agent.cli import main, render_html
from value_investing_agent.config import Settings, require_credentials
from value_investing_agent.prompts import research_instruction
from value_investing_agent.research import ResearchResult, ResearchTimeoutError


@pytest.fixture
def result():
    return ResearchResult(
        query="Analyze AAPL",
        model="gemini-flash-latest",
        retrieved_at_utc="2026-11-10T12:00:00+00:00",
        report="Stock research <script>unsafe()</script>",
        grounding_metadata=[
            {
                "grounding_chunks": [
                    {"web": {"title": "A & B", "uri": "https://example.com/quote"}},
                    {"web": {"title": "duplicate", "uri": "https://example.com/quote"}},
                    {"web": {"title": "invalid", "uri": "javascript:alert(1)"}},
                ],
                "search_entry_point": {"rendered_content": "<div>Google suggestions</div>"},
            }
        ],
    )


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("GEMINI_MODEL=gemini-from-file\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-from-environment")
    assert Settings.from_env().model == "gemini-from-environment"


def test_loads_project_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    (tmp_path / ".env").write_text("GEMINI_MODEL=gemini-from-file\n", encoding="utf-8")
    assert Settings.from_env().model == "gemini-from-file"
    monkeypatch.delenv("GEMINI_MODEL")


def test_rejects_non_gemini_model(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "other-model")
    with pytest.raises(ValueError, match="Gemini model ID"):
        Settings.from_env()


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        require_credentials()


def test_agent_uses_native_google_search():
    agent = create_agent(Settings(model="gemini-test"))
    assert agent.model == "gemini-test"
    assert agent.tools == [google_search]
    assert "Current research time (UTC)" in research_instruction(None)


def test_html_escapes_report_and_preserves_google_suggestions(result):
    output = render_html(result)
    assert "<script>unsafe()" not in output
    assert "&lt;script&gt;" in output
    assert "<div>Google suggestions</div>" in output
    assert "A &amp; B" in output
    assert "javascript:" not in output
    assert len(result.sources) == 1


@pytest.mark.parametrize("suffix", ["md", "json", "html"])
def test_cli_export(suffix, tmp_path, result):
    output = tmp_path / "reports" / f"analysis.{suffix}"
    with patch("value_investing_agent.cli.analyze", new=AsyncMock(return_value=result)):
        assert main(["Analyze AAPL", "--output", str(output)]) == 0
    content = output.read_text(encoding="utf-8")
    if suffix == "json":
        assert json.loads(content) == result.to_dict()
    else:
        assert "https://example.com/quote" in content


@pytest.mark.parametrize("timeout", ["0", "-10", "nan", "inf"])
def test_cli_rejects_invalid_timeout(timeout):
    with pytest.raises(SystemExit) as error:
        main(["AAPL", "--timeout", timeout])
    assert error.value.code == 2


def test_cli_rejects_unknown_format():
    with pytest.raises(SystemExit) as error:
        main(["AAPL", "--output", "report.txt"])
    assert error.value.code == 2


@pytest.mark.parametrize("exception_type", [RuntimeError, ValueError])
def test_cli_hides_api_exception_details(capsys, exception_type):
    with patch(
        "value_investing_agent.cli.analyze",
        new=AsyncMock(
            side_effect=exception_type("request?key=secret"),
        ),
    ):
        assert main(["AAPL"]) == 1
    captured = capsys.readouterr()
    assert "secret" not in captured.err
    assert "API key" in captured.err


def test_cli_timeout(capsys):
    with patch("value_investing_agent.cli.analyze", new=AsyncMock(side_effect=TimeoutError())):
        assert main(["AAPL"]) == 1
    assert "timed out" in capsys.readouterr().err


def test_cli_preserves_safe_timeout_explanation(capsys):
    message = "Research timed out after 300 seconds while waiting for Gemini's report."
    with patch(
        "value_investing_agent.cli.analyze",
        new=AsyncMock(side_effect=ResearchTimeoutError(message)),
    ) as run:
        assert main(["AAPL"]) == 1
    run.assert_awaited_once_with("AAPL", timeout=300)
    assert message in capsys.readouterr().err
