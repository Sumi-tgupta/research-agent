"""
Tests for the Phase-12 model router — the piece that decides *which* provider
serves a call and *falls back* to the other one when the first fails.

These are the only tests that exercise the Groq path directly, so they each
re-patch ``app.model_router.get_groq_client`` in their own body, overriding the
autouse fixture in conftest.py that otherwise neutralizes Groq for the
per-agent tests. Both providers are faked at their real SDK shapes:

  - Gemini: ``client.models.generate_content(...).text``
  - Groq:   ``client.chat.completions.create(...).choices[0].message.content``

so this verifies the router's own dispatch/fallback wiring without a live model.
"""

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.model_router import RouterError, Tier, generate_structured, generate_text


class _Answer(BaseModel):
    value: int


def _routing_on_settings() -> Settings:
    """Routing enabled with both providers' model names populated — the only
    settings fields the router actually reads."""
    return Settings.model_construct(
        llm_routing_enabled=True,
        gemini_model="gemini-2.5-flash",
        groq_model="llama-3.3-70b-versatile",
        groq_fast_model="llama-3.1-8b-instant",
    )


def _fake_gemini(text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=text)
    return client


def _fake_groq(content: str) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return client


def test_heavy_tier_prefers_gemini_and_does_not_touch_groq(mocker):
    mocker.patch("app.retry.time.sleep")
    mocker.patch("app.model_router.get_settings", return_value=_routing_on_settings())
    gemini = _fake_gemini("from gemini")
    groq = _fake_groq("from groq")
    mocker.patch("app.model_router.get_gemini_client", return_value=gemini)
    mocker.patch("app.model_router.get_groq_client", return_value=groq)

    out = generate_text("prompt", tier=Tier.HEAVY)

    assert out == "from gemini"
    gemini.models.generate_content.assert_called_once()
    groq.chat.completions.create.assert_not_called()


def test_light_tier_prefers_groq_and_does_not_touch_gemini(mocker):
    mocker.patch("app.model_router.get_settings", return_value=_routing_on_settings())
    gemini = _fake_gemini("from gemini")
    groq = _fake_groq("from groq")
    mocker.patch("app.model_router.get_gemini_client", return_value=gemini)
    mocker.patch("app.model_router.get_groq_client", return_value=groq)

    out = generate_text("prompt", tier=Tier.LIGHT)

    assert out == "from groq"
    groq.chat.completions.create.assert_called_once()
    gemini.models.generate_content.assert_not_called()


def test_falls_back_to_groq_when_gemini_fails_and_notes_it(mocker):
    mocker.patch("app.retry.time.sleep")  # non-retryable error shouldn't sleep, but be safe
    mocker.patch("app.model_router.get_settings", return_value=_routing_on_settings())
    gemini = MagicMock()
    gemini.models.generate_content.side_effect = RuntimeError("gemini unavailable")
    groq = _fake_groq("recovered via groq")
    mocker.patch("app.model_router.get_gemini_client", return_value=gemini)
    mocker.patch("app.model_router.get_groq_client", return_value=groq)

    warnings: list[str] = []
    out = generate_text("prompt", tier=Tier.HEAVY, warnings=warnings)

    assert out == "recovered via groq"
    # the fallback is surfaced, not silent
    assert any("fell back to groq" in w for w in warnings)


def test_kill_switch_routes_everything_to_gemini(mocker):
    mocker.patch(
        "app.model_router.get_settings",
        return_value=Settings.model_construct(
            llm_routing_enabled=False,
            gemini_model="gemini-2.5-flash",
            groq_model="llama-3.3-70b-versatile",
            groq_fast_model="llama-3.1-8b-instant",
        ),
    )
    gemini = _fake_gemini("gemini only")
    groq = _fake_groq("should never be reached")
    mocker.patch("app.model_router.get_gemini_client", return_value=gemini)
    mocker.patch("app.model_router.get_groq_client", return_value=groq)

    # Even a LIGHT-tier call must stay on Gemini when routing is disabled.
    out = generate_text("prompt", tier=Tier.LIGHT)

    assert out == "gemini only"
    groq.chat.completions.create.assert_not_called()


def test_structured_invalid_json_from_primary_falls_back_and_validates(mocker):
    mocker.patch("app.retry.time.sleep")
    mocker.patch("app.model_router.get_settings", return_value=_routing_on_settings())
    gemini = _fake_gemini("this is not json")  # HEAVY primary: unparseable
    groq = _fake_groq('{"value": 42}')  # HEAVY fallback: valid
    mocker.patch("app.model_router.get_gemini_client", return_value=gemini)
    mocker.patch("app.model_router.get_groq_client", return_value=groq)

    warnings: list[str] = []
    out = generate_structured("prompt", tier=Tier.HEAVY, schema=_Answer, warnings=warnings)

    # schema-invalid output from the primary counts as a provider failure, so
    # the router falls through to the provider that returns valid JSON
    assert out.value == 42
    assert any("fell back to groq" in w for w in warnings)


def test_light_structured_uses_groq_json_mode_with_schema_inlined(mocker):
    mocker.patch("app.model_router.get_settings", return_value=_routing_on_settings())
    groq = _fake_groq('{"value": 7}')
    mocker.patch("app.model_router.get_gemini_client", return_value=None)
    mocker.patch("app.model_router.get_groq_client", return_value=groq)

    out = generate_structured("prompt", tier=Tier.LIGHT, schema=_Answer)

    assert out.value == 7
    kwargs = groq.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    # the JSON Schema is handed to the small model in a system message
    assert any(m["role"] == "system" for m in kwargs["messages"])


def test_raises_router_error_when_no_provider_is_configured(mocker):
    mocker.patch("app.model_router.get_settings", return_value=_routing_on_settings())
    mocker.patch("app.model_router.get_gemini_client", return_value=None)
    mocker.patch("app.model_router.get_groq_client", return_value=None)

    with pytest.raises(RouterError):
        generate_text("prompt", tier=Tier.HEAVY)
