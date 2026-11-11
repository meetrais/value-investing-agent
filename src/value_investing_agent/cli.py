"""Terminal entry point and portable research report exports."""

import argparse
import asyncio
import html
import json
import math
import sys
from pathlib import Path

from .config import DEFAULT_RESEARCH_TIMEOUT, ConfigurationError
from .research import ResearchError, ResearchResult, ResearchTimeoutError, analyze


def render_markdown(result: ResearchResult) -> str:
    sources = "\n".join(f"- {source['title']}: <{source['uri']}>" for source in result.sources)
    return (
        f"{result.report}\n\n---\nRetrieved at (UTC): {result.retrieved_at_utc}\n"
        f"Model: {result.model}\n\nGoogle Search grounding sources:\n{sources}\n"
    )


def render_html(result: ResearchResult) -> str:
    # Escape model output. Google's search-entry HTML is preserved as returned
    # by the grounding service so its search suggestions remain displayable.
    sources = "\n".join(
        f'<li><a href="{html.escape(s["uri"], quote=True)}">{html.escape(s["title"])}</a></li>'
        for s in result.sources
    )
    suggestions = "\n".join(result.search_suggestions)
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Value investing research</title>"
        "<style>body{max-width:960px;margin:3rem auto;padding:0 1rem;"
        "font:16px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere;"
        "font:inherit}a{overflow-wrap:anywhere}</style><body>"
        f"<pre>{html.escape(result.report)}</pre>"
        f"<p>Retrieved at (UTC): {html.escape(result.retrieved_at_utc)}"
        f" | Model: {html.escape(result.model)}</p>"
        f"<h2>Google Search sources</h2><ul>{sources}</ul>{suggestions}</body></html>"
    )


def positive_timeout(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Research stocks with Gemini and Google Search.")
    parser.add_argument("query", help='Ticker, company, or question, e.g. "Analyze NYSE:BRK.B"')
    parser.add_argument(
        "--output", type=Path, help="Save .md, .json (with metadata), or .html report"
    )
    parser.add_argument(
        "--timeout", type=positive_timeout, default=DEFAULT_RESEARCH_TIMEOUT,
        help="Request timeout in seconds (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    if args.output and args.output.suffix.lower() not in {".md", ".json", ".html"}:
        parser.error("--output must end in .md, .json, or .html")
    try:
        result = asyncio.run(analyze(args.query, timeout=args.timeout))
        if args.output:
            suffix = args.output.suffix.lower()
            if suffix == ".json":
                content = json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n"
            elif suffix == ".html":
                content = render_html(result)
            else:
                content = render_markdown(result)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(f"Saved research to {args.output}")
        else:
            print(render_markdown(result))
        return 0
    except ResearchTimeoutError as exc:
        print(str(exc), file=sys.stderr)
    except TimeoutError:
        print("Research timed out. Retry or increase --timeout.", file=sys.stderr)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 -- sanitize exceptions at the CLI boundary
        # API exceptions can contain request URLs/credentials. Never echo them.
        if isinstance(exc, (ConfigurationError, ResearchError, OSError)):
            print(f"Research failed: {exc}", file=sys.stderr)
        else:
            print(
                "Research failed: Check your API key, model access, quota, and network connection.",
                file=sys.stderr,
            )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
