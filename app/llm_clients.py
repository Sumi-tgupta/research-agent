"""
LLM client factory + a one-line smoke test for each provider.

Phase 1's agents (Search, Paper Retrieval) don't call an LLM at all — they're
pure API wrappers. This module exists so Phase 0's "get the keys working" is
verifiable today, ahead of Phase 2 (Planner) and Phase 4 (Writer/Reviewer)
which will actually depend on it.

Gemini note: Google now also offers a newer "Interactions API" (recommended
for brand-new agentic projects). We use the classic `generate_content` call
here because it's simpler and fully supported, which is all a single
routing/writing call needs. Worth revisiting if we later want Gemini's
built-in Google Search grounding or its managed Deep Research agent.
"""

from google import genai
from groq import Groq

from app.config import get_settings


def get_gemini_client() -> genai.Client | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    return genai.Client(api_key=settings.gemini_api_key)


def get_groq_client() -> Groq | None:
    settings = get_settings()
    if not settings.groq_api_key:
        return None
    return Groq(api_key=settings.groq_api_key)


def gemini_smoke_test(prompt: str = "Reply with exactly: pong") -> str:
    """Round-trips one prompt through Gemini. Raises if the key is missing/bad."""
    client = get_gemini_client()
    if client is None:
        raise RuntimeError("GEMINI_API_KEY not configured")
    settings = get_settings()
    response = client.models.generate_content(model=settings.gemini_model, contents=prompt)
    return response.text


def groq_smoke_test(prompt: str = "Reply with exactly: pong") -> str:
    """Round-trips one prompt through Groq. Raises if the key is missing/bad."""
    client = get_groq_client()
    if client is None:
        raise RuntimeError("GROQ_API_KEY not configured")
    settings = get_settings()
    completion = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content
