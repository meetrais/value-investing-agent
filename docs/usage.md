# Value investing agent usage guide

[Back to the project overview](../README.md).

A Python AI agent built with **Google ADK**, a **Gemini model**, and Gemini's
native **Google Search grounding**. It researches current stock prices, price
trends, news, company fundamentals, business quality, and valuation from the web.
No separate search API key or market-data subscription is required.

The agent produces a research memo with sourced facts, fiscal periods, valuation
scenarios, margin of safety, risks, catalysts, and a conditional assessment. It
looks for primary filings and investor-relations releases and distinguishes
reported figures from estimates and assumptions. Valuation calculations are
model-generated and should be independently verified.

## Setup

Requires Python 3.11+ and a [Gemini API key](https://aistudio.google.com/apikey)
with access to a model supporting Google Search grounding. API usage and search
grounding may incur charges according to your Google plan.

Run all commands in this guide from the repository root. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Set `GOOGLE_API_KEY` in `.env`. The file is ignored by Git. Environment variables
override `.env`. `GEMINI_API_KEY` is also accepted by the Google SDK.

```dotenv
GOOGLE_API_KEY=your-key-here
GEMINI_MODEL=gemini-flash-latest
```

The default follows Google's Flash model alias. Set `GEMINI_MODEL` to a specific
search-capable Gemini model ID if you need predictable model selection. This
project's setup uses the Gemini Developer API, rather than Vertex AI credentials.

On macOS/Linux, use `.venv/bin/python` and `.venv/bin/adk` in place of the Windows
executables below, and `cp .env.example .env` to create the configuration file.

## Browser interface (default)

Start the local web server:

```powershell
.\.venv\Scripts\python.exe -m value_investing_agent
```

Open **http://127.0.0.1:8000** in your browser. The installed command
`value-investing-agent` starts the same interface. Use `--port 8080` to choose
another port. The server binds to your local computer; keep the terminal running
and press `Ctrl+C` to stop it.

1. Enter a ticker, company, comparison, or investment question. Example buttons
   fill in a question for you to edit before submitting.
2. Choose a research time limit (five minutes by default) and select **Begin research**. The page shows a
   loading state while Gemini researches the question.
3. Read the memo, inspect Google Search sources and suggestions, and download a
   Markdown, HTML, or JSON report using **Save report**.

The server reads the API key from `.env` or the environment. The browser never
receives the key. Requests use the same `analyze()` pipeline as terminal exports,
including the requirement for Google Search sources. Configuration errors,
timeouts, and failed requests appear on the page, where you can retry. Each
question starts a separate research session; previous memos are not persisted.
Submitting another question replaces the displayed memo after it succeeds.

## Optional terminal exports

```powershell
.\.venv\Scripts\python.exe -m value_investing_agent.cli "Analyze NYSE:BRK.B as a value investment"
.\.venv\Scripts\python.exe -m value_investing_agent.cli "Compare NASDAQ:GOOGL and NASDAQ:MSFT: quality, valuation, and downside"
.\.venv\Scripts\python.exe -m value_investing_agent.cli "Analyze NYSE:KO with bear/base/bull valuation scenarios" --output reports/ko.html --timeout 240
.\.venv\Scripts\python.exe -m value_investing_agent.cli "Analyze NASDAQ:AAPL" --output reports/aapl.json
```

After activating the environment, the equivalent installed command is
`value-investing-agent-cli "Analyze NASDAQ:AAPL"`.

Output formats:

| Format | Contents |
| --- | --- |
| Terminal / `.md` | Research text, retrieval time, model, and grounding source links |
| `.html` | Escaped report text, clickable sources, and Google's returned Search Suggestions HTML |
| `.json` | Report plus original grounding metadata, including queries, source chunks, claim-support mappings, and Search Suggestions |

Open an HTML export in your browser to view Google's Search Suggestions. A custom
frontend consuming the JSON should render Google's `search_entry_point.rendered_content`
and use `grounding_supports` to connect claims to sources. The source appendix
lists retrieved pages; it does not assert that every claim was verified.

Each terminal invocation starts an isolated in-memory session. A report with no
Google Search sources is withheld and exits with an error. This checks for
grounding evidence, not the accuracy or freshness of each individual figure.
The timeout defaults to 300 seconds. Authentication, quota, model availability,
or network failures produce a nonzero exit code.

### Research timeouts (HTTP 504)

A full memo or company comparison can take several minutes. If the selected
time limit expires, choose **10 minutes** or narrow the question to one company
or topic. The error shows the selected limit and the stage that timed out. If
Gemini's upstream request times out first, the error identifies that separately;
check connectivity and retry later. The terminal logs the model, limit, stage,
and number of received events without printing the API key or raw SDK error.

After changing `.env` or updating the application, stop the server with `Ctrl+C`,
start it again, and refresh the browser. Only copy `.env.example` during initial
setup; copying it again replaces your existing configuration.

## Optional ADK development UI

ADK discovers `value_investing_agent.agent.root_agent`. From the repository root:

```powershell
.\.venv\Scripts\adk.exe run src/value_investing_agent
.\.venv\Scripts\adk.exe web src
```

For the web UI, open the local address printed by ADK and select
`value_investing_agent`. Ask follow-up questions in the same session, for example:
“What would invalidate the thesis?” or “How does the valuation change under
slower revenue growth?” ADK manages conversation context. These development
interfaces use ADK's own event handling; the terminal wrapper's explicit
no-grounding rejection applies only to `analyze()` and the project CLI.

## How it works

- `agent.py` creates a Gemini-backed ADK `Agent` with `tools=[google_search]`.
  Google executes the searches natively; there is no simulated search tool,
  third-party search wrapper, or hardcoded stock data.
- `prompts.py` supplies the current UTC research time on every invocation and
  defines evidence, freshness, fundamentals, DCF, sector-specific valuation,
  margin-of-safety, and counter-thesis requirements.
- `research.py` runs a request through ADK's `InMemoryRunner`, captures grounding
  metadata across events, filters thought parts, enforces a timeout, and closes
  the runner. Sessions are not persisted after the process ends.
- `web.py` serves the browser interface and research endpoint with FastAPI.
  Packaged HTML, CSS, and JavaScript under `static/` provide the form, loading and
  error states, sandboxed report viewer, source index, and browser downloads.
- `cli.py` provides optional terminal exports as Markdown, HTML, or JSON.

Native Google Search is the sole agent tool to avoid model-dependent restrictions
on mixing built-in search and custom function tools. Gemini decides which searches
to execute; the instructions require fresh research for securities questions.
Search may return delayed quotes, incomplete financials, or conflicting results.
The agent is instructed to label those limitations and withhold unsupported
valuations. It does not connect to a brokerage or place orders.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

Default tests run without network access or API calls. They cover configuration,
native search wiring, real ADK event schemas, grounding preservation, missing
evidence, timeouts, session isolation, exports, and safe error output.

To explicitly run the live Gemini search test using your API quota:

```powershell
$env:RUN_LIVE_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -m live
Remove-Item Env:RUN_LIVE_TESTS
```

Research only; not personalized financial advice. Verify sources, quote timestamps,
and calculations before making investment decisions.

References: [ADK Google Search grounding](https://adk.dev/grounding/google_search_grounding/),
[Gemini Google Search grounding](https://ai.google.dev/gemini-api/docs/google-search),
[Gemini model catalog](https://ai.google.dev/gemini-api/docs/models).
