"""Native Gemini Google Search grounding, without third-party search APIs."""

from google.adk.agents import Agent
from google.adk.tools import google_search
from google.genai import types

from .config import Settings
from .prompts import research_instruction


def create_agent(settings: Settings | None = None) -> Agent:
    settings = settings or Settings.from_env()
    return Agent(
        name="value_investing_agent",
        model=settings.model,
        description="Search-grounded stock fundamentals, news, trends and value investing research.",
        instruction=research_instruction,
        # Keep native search as the sole tool; some Gemini versions prohibit
        # combining built-in search with custom function tools in one agent.
        tools=[google_search],
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
    )


root_agent = create_agent()
