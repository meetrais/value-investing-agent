"""Local browser interface for search-grounded investment research."""

import argparse
import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .cli import render_html, render_markdown
from .config import DEFAULT_RESEARCH_TIMEOUT, ConfigurationError
from .research import ResearchError, ResearchTimeoutError, analyze

STATIC_DIR = Path(__file__).with_name("static")
app = FastAPI(title="Value investing research", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    timeout: float = Field(default=DEFAULT_RESEARCH_TIMEOUT, ge=10, le=600, allow_inf_nan=False)

    @field_validator("query")
    @classmethod
    def trim_query(cls, query: str) -> str:
        if not query.strip():
            raise ValueError("Provide a ticker, company, or research question.")
        return query.strip()


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/research")
async def research(payload: ResearchRequest, request: Request) -> dict:
    # Only the local page should initiate browser requests that consume API quota.
    origin = request.headers.get("origin")
    expected_origin = f"{request.url.scheme}://{request.url.netloc}"
    if origin and origin != expected_origin:
        raise HTTPException(status_code=403, detail="Use the research page on this server.")
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(status_code=415, detail="Send a JSON research request.")
    try:
        result = await analyze(payload.query, timeout=payload.timeout)
    except ResearchTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from None
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="The upstream request timed out. Try again or check your network connection.",
        ) from None
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except ResearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except Exception:  # noqa: BLE001 -- never send SDK credentials or request URLs to the browser
        raise HTTPException(
            status_code=502,
            detail="Research failed. Check your API key, model access, quota, and network connection.",
        ) from None
    data = result.to_dict()
    return {
        **data,
        "sources": result.sources,
        "exports": {
            "md": render_markdown(result),
            "html": render_html(result),
            "json": json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open the value investing web interface.")
    parser.add_argument("--host", choices=["127.0.0.1", "localhost", "::1"], default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    display_host = f"[{args.host}]" if ":" in args.host else args.host
    print(f"Open http://{display_host}:{args.port} in your browser.", flush=True)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0
