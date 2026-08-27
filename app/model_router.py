"""
Multi-model router — one place that decides *which* LLM serves a given call
and *falls back* to the other provider when the first one fails.

Why this exists
---------------
The pipeline has two very different kinds of LLM work:

  - "heavy" reasoning — planning the sub-questions, writing the report,
    reviewing the draft. These want the strongest model available.
  - "light" extraction — pulling candidate claims out of sources, spotting
    chartable numbers. These are narrow, mechanical tasks a small fast model
    handles well.

Gemini's free tier is the scarce resource (low daily request cap), so when
routing is enabled and a Groq key is present we spend it only on the heavy
stages and push the light, high-volume extraction onto Groq's fast small
model. Every call also has a *fallback* provider: if the primary errors
(rate limit, 5xx, network, or — for structured calls — returns JSON that
doesn't validate), the router transparently retries the same prompt on the
other provider before giving up. That turns "Gemini hit its daily cap" from
a pipeline-stopping failure into a silent switch to Groq.

Routing policy
--------------
  Tier.HEAVY  (planner, writer, reviewer):        Gemini  ->  Groq(groq_model)
  Tier.LIGHT  (fact-check extraction, charts):     Groq(groq_fast_model) -> Gemini

When ``settings.llm_routing_enabled`` is False the router collapses to
Gemini-only — byte-for-byte the pre-Phase-12 behavior — so the flag is a
true kill switch. When it's True but a provider has no key configured, that
provider is simply skipped (not counted as a failure), so "routing on but no
Groq key" cleanly runs everything on Gemini, exactly as the config comment
promises.

Provider differences this hides from callers
--------------------------------------------
Gemini takes a Pydantic model directly as ``response_schema`` and returns
JSON. Groq (OpenAI-shaped) has no native schema binding, so for structured
calls we run its JSON mode (``response_format={"type": "json_object"}``) and
inline the model's JSON Schema in a system message. Both paths are wrapped
in the same exponential backoff (retry.py) used everywhere else, and both
guarantee a non-empty response. Callers just ask for text or a parsed model
and never see which provider answered.
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Callable, TypeVar

from google.genai import types as genai_types
from pydantic import BaseModel

from app.config import get_settings
from app.llm_clients import get_gemini_client, get_groq_client
from app.retry import call_with_backoff, is_retryable_http_error

M = TypeVar("M", bound=BaseModel)

GEMINI = "gemini"
GROQ = "groq"


class Tier(str, Enum):
    """Which class of work a call is, and therefore how it should be routed.
    HEAVY prefers Gemini (strongest), LIGHT prefers Groq's fast model (cheap,
    high-volume extraction). See the module docstring for the full policy."""

    HEAVY = "heavy"
    LIGHT = "light"


class RouterError(RuntimeError):
    """Raised only when *every* eligible provider failed, or none was
    configured at all. Wraps the per-provider error strings so the calling
    agent can report what actually went wrong in its own error list before
    falling back to its deterministic no-LLM path."""


@dataclass(frozen=True)
class _Attempt:
    provider: str  # GEMINI | GROQ
    model: str


def _provider_chain(tier: Tier, settings) -> list[_Attempt]:
    """The ordered list of (provider, model) to try for this tier. First
    entry is the primary; the rest are fallbacks tried in order."""
    gemini = _Attempt(GEMINI, settings.gemini_model)
    if not settings.llm_routing_enabled:
        # Kill switch: pre-Phase-12 behavior — Gemini only, no fallback.
        return [gemini]
    if tier == Tier.LIGHT:
        return [_Attempt(GROQ, settings.groq_fast_model), gemini]
    return [gemini, _Attempt(GROQ, settings.groq_model)]


def _client_for(provider: str, gemini_getter: Callable[[], object]):
    """The live SDK client for a provider, or None when its key is unset.

    ``gemini_getter`` is injected (it defaults, in _run_chain, to this module's
    own get_gemini_client) so each agent can pass its own client factory. That
    is the seam the per-agent tests patch — e.g. patching
    ``app.agents.planner_agent.get_gemini_client`` still intercepts the call
    because the planner hands that function to the router. Groq has no such
    per-agent seam and always uses the shared get_groq_client."""
    return gemini_getter() if provider == GEMINI else get_groq_client()


def _gemini_generate(client, prompt: str, model: str, response_schema: type[BaseModel] | None) -> str:
    """One Gemini call, wrapped in shared backoff. Uses Gemini's native
    Pydantic ``response_schema`` for structured output. Raises on an empty
    response so an empty answer counts as a failure worth falling back for."""
    config = None
    if response_schema is not None:
        config = genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
        )
    response = call_with_backoff(
        lambda: client.models.generate_content(model=model, contents=prompt, config=config),
        is_retryable=is_retryable_http_error,
    )
    text = response.text
    if not text or not text.strip():
        raise ValueError("Gemini returned an empty response")
    return text


def _groq_generate(client, prompt: str, model: str, response_schema: type[BaseModel] | None) -> str:
    """One Groq call, wrapped in shared backoff. Groq has no native schema
    binding, so structured calls use JSON mode with the model's JSON Schema
    inlined in a system message (JSON mode also *requires* the word "json"
    in the messages, which that instruction satisfies)."""
    kwargs: dict = {"model": model}
    if response_schema is not None:
        schema = json.dumps(response_schema.model_json_schema())
        kwargs["messages"] = [
            {
                "role": "system",
                "content": (
                    "You are a strict JSON generator. Respond with ONLY a single JSON "
                    "object that validates against the JSON Schema below. Do not wrap it "
                    "in markdown fences, and do not add any commentary before or after.\n\n"
                    "JSON Schema:\n" + schema
                ),
            },
            {"role": "user", "content": prompt},
        ]
        kwargs["response_format"] = {"type": "json_object"}
    else:
        kwargs["messages"] = [{"role": "user", "content": prompt}]

    response = call_with_backoff(
        lambda: client.chat.completions.create(**kwargs),
        is_retryable=is_retryable_http_error,
    )
    text = response.choices[0].message.content
    if not text or not text.strip():
        raise ValueError("Groq returned an empty response")
    return text


def _dispatch(provider: str, client, prompt: str, model: str, response_schema: type[BaseModel] | None) -> str:
    if provider == GEMINI:
        return _gemini_generate(client, prompt, model, response_schema)
    return _groq_generate(client, prompt, model, response_schema)


def _run_chain(
    prompt: str,
    tier: Tier,
    *,
    response_schema: type[BaseModel] | None,
    parse: Callable[[str], object] | None,
    warnings: list[str] | None,
    gemini_client_factory: Callable[[], object] | None = None,
):
    """Walk the tier's provider chain, returning the first provider's result
    that both responds and (when ``parse`` is given) parses successfully.

    A provider with no configured key is skipped silently — it isn't a
    failure, just not part of this deployment's routing. A provider that
    raises, returns empty, or produces output ``parse`` rejects is recorded
    and the next provider is tried. If a *later* provider succeeds after an
    earlier one failed, a one-line note is appended to ``warnings`` so the
    fallback is visible in the run's error/warning feed rather than silent.

    ``gemini_client_factory`` lets the calling agent supply the client getter
    the router should use for Gemini (defaulting to this module's
    get_gemini_client); see _client_for for why the agents pass their own.

    Raises RouterError only when nothing configured could produce a usable
    result; the calling agent then uses its own deterministic fallback."""
    settings = get_settings()
    chain = _provider_chain(tier, settings)
    gemini_getter = gemini_client_factory or get_gemini_client
    errors: list[str] = []
    attempted = 0

    for attempt in chain:
        client = _client_for(attempt.provider, gemini_getter)
        if client is None:
            continue
        attempted += 1
        try:
            text = _dispatch(attempt.provider, client, prompt, attempt.model, response_schema)
            value = parse(text) if parse is not None else text
        except Exception as exc:
            errors.append(f"{attempt.provider}:{attempt.model} failed: {exc}")
            continue
        if warnings is not None and errors:
            warnings.append(
                f"LLM routing: primary provider failed ({'; '.join(errors)}); "
                f"fell back to {attempt.provider}:{attempt.model}"
            )
        return value

    if attempted == 0:
        raise RouterError("no LLM provider configured (set GEMINI_API_KEY or GROQ_API_KEY)")
    raise RouterError("all LLM providers failed — " + "; ".join(errors))


def generate_text(
    prompt: str,
    *,
    tier: Tier,
    warnings: list[str] | None = None,
    gemini_client_factory: Callable[[], object] | None = None,
) -> str:
    """Free-form text generation (e.g. the Writer's draft). Returns the raw
    model text, or raises RouterError if every eligible provider failed.
    ``gemini_client_factory`` is the agent's own get_gemini_client, passed so
    per-agent test patches keep working (see _client_for)."""
    return _run_chain(
        prompt,
        tier,
        response_schema=None,
        parse=None,
        warnings=warnings,
        gemini_client_factory=gemini_client_factory,
    )


def generate_structured(
    prompt: str,
    *,
    tier: Tier,
    schema: type[M],
    warnings: list[str] | None = None,
    gemini_client_factory: Callable[[], object] | None = None,
) -> M:
    """Structured generation validated against ``schema``. Returns a parsed
    instance of ``schema``. Because parsing happens inside the provider loop,
    JSON that doesn't validate is treated as that provider failing and
    triggers fallback to the next provider — so a caller that gets a value
    back is guaranteed a well-formed model. Raises RouterError if no provider
    could produce schema-valid output. ``gemini_client_factory`` is the
    agent's own get_gemini_client (see _client_for)."""
    return _run_chain(
        prompt,
        tier,
        response_schema=schema,
        parse=schema.model_validate_json,
        warnings=warnings,
        gemini_client_factory=gemini_client_factory,
    )
