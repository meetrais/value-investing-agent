"""Exercise the actual ADK runner, replacing only the network model response."""

import asyncio
from collections.abc import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field

from value_investing_agent.agent import create_agent
from value_investing_agent.config import Settings
from value_investing_agent.research import analyze


class OfflineGemini(BaseLlm):
    model: str = "gemini-flash-latest"
    requests: list[LlmRequest] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text="Offline grounded report.")]
            ),
            grounding_metadata=types.GroundingMetadata(
                web_search_queries=["AAPL quote"],
                grounding_chunks=[
                    types.GroundingChunk(
                        web=types.GroundingChunkWeb(title="Quote", uri="https://example.com/quote"),
                    )
                ],
            ),
        )


def test_actual_adk_runner_enables_native_search(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "offline-key-never-sent")
    model = OfflineGemini()
    agent = create_agent(Settings())
    agent.model = model
    monkeypatch.setattr("value_investing_agent.research.create_agent", lambda _settings: agent)
    result = asyncio.run(analyze("Analyze NASDAQ:AAPL", settings=Settings()))
    assert result.report == "Offline grounded report."
    assert result.sources[0]["uri"] == "https://example.com/quote"
    assert len(model.requests) == 1
    request = model.requests[0]
    assert any(tool.google_search is not None for tool in request.config.tools)
    assert "Current research time (UTC)" in str(request.config.system_instruction)
    assert "Analyze NASDAQ:AAPL" in request.contents[-1].parts[0].text
