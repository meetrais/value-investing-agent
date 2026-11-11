# Value investing agent

A Python research agent built with Google ADK, Gemini, and native Google Search
grounding. It researches stock prices, fundamentals, news, business quality, and
valuation through a browser-based interface, with sourced reports and Markdown,
HTML, or JSON downloads.

## Quick start

Requires Python 3.11+ and a [Gemini API key](https://aistudio.google.com/apikey)
with access to a model supporting Google Search grounding. API usage and search
grounding may incur charges according to your Google plan.

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Set `GOOGLE_API_KEY` in `.env`, then run:

```powershell
.\.venv\Scripts\python.exe -m value_investing_agent
```

Open **http://127.0.0.1:8000** in your browser. Enter a ticker, company, or
investment question, then select **Begin research**. Review the memo and its
sources, or download the report as Markdown, HTML, or JSON. Keep the server
running while you use the page; press `Ctrl+C` in the terminal to stop it.
Use `--port 8080` if port 8000 is already in use.

After installing, `value-investing-agent` starts the same web interface.
API keys stay on the Python server; the browser never needs your key.

On macOS/Linux, use `.venv/bin/python` and `cp .env.example .env`.

See the [usage guide](docs/usage.md) for configuration, browser workflow,
optional terminal exports, implementation details, and live test instructions.

## Project layout

```text
value-investing-agent/
├── src/
│   └── value_investing_agent/  # Agent, configuration, research, and CLI
├── tests/
│   ├── unit/                  # Configuration, CLI, and mocked research tests
│   ├── integration/           # Actual ADK runtime with an offline model
│   └── live/                  # Opt-in Gemini API test
├── docs/
│   └── usage.md               # Detailed setup, usage, and architecture
├── .env.example               # Configuration template
├── pyproject.toml             # Packaging and tool configuration
├── README.md
└── LICENSE
```

Install the package with the editable install above before running commands or
tests. Keep `.env` in the repository root; environment variables override it.
The browser saves exported reports to your downloads folder. For optional
terminal exports, use `value-investing-agent-cli` with `--output`.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

The default suite runs offline; the live test requires `RUN_LIVE_TESTS=1` and uses
API quota. Run a specific test group with `pytest tests/unit` or
`pytest tests/integration`.

Research only; not personalized financial advice. Verify sources, quote timestamps,
and calculations before making investment decisions.
