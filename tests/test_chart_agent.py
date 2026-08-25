"""
Tests for the Chart Agent. Mirrors the Fact Checker's testing philosophy:
mock only the Gemini call, and specifically verify the defensive filter
that drops malformed chart specs (mismatched labels/values length) rather
than letting them reach matplotlib.
"""

from unittest.mock import MagicMock

from app.agents.chart_agent import ChartAgent
from app.schemas import ClaimVerdict, VerifiedClaim


def _claim(text: str, sub_question: str = "q1") -> VerifiedClaim:
    return VerifiedClaim(text=text, sub_question=sub_question, verdict=ClaimVerdict.CORROBORATED, confidence=0.7)


def _fake_gemini_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=response_text)
    return client


def test_extracts_a_valid_chart(mocker):
    mocker.patch(
        "app.agents.chart_agent.get_gemini_client",
        return_value=_fake_gemini_client(
            '{"charts": [{"title": "Reported caffeine half-life", "chart_type": "bar", '
            '"x_label": "Source", "y_label": "Hours", "labels": ["Review A", "Study B"], "values": [5, 9.5]}]}'
        ),
    )

    charts, errors = ChartAgent().extract([_claim("Half-life estimates vary between 5 and 9.5 hours.")])

    assert errors == []
    assert len(charts) == 1
    assert charts[0].title == "Reported caffeine half-life"
    assert charts[0].labels == ["Review A", "Study B"]
    assert charts[0].values == [5.0, 9.5]


def test_no_claims_short_circuits_without_calling_gemini(mocker):
    gemini_mock = mocker.patch("app.agents.chart_agent.get_gemini_client")

    charts, errors = ChartAgent().extract([])

    assert charts == []
    assert errors == []
    gemini_mock.assert_not_called()


def test_no_key_returns_empty_list_with_clear_error(mocker):
    mocker.patch("app.agents.chart_agent.get_gemini_client", return_value=None)

    charts, errors = ChartAgent().extract([_claim("Some claim.")])

    assert charts == []
    assert any("GEMINI_API_KEY" in e for e in errors)


def test_malformed_json_returns_empty_list_not_a_crash(mocker):
    mocker.patch("app.agents.chart_agent.get_gemini_client", return_value=_fake_gemini_client("not json"))

    charts, errors = ChartAgent().extract([_claim("Some claim.")])

    assert charts == []
    assert any("Chart extraction failed" in e for e in errors)


def test_empty_charts_list_is_a_normal_clean_outcome(mocker):
    mocker.patch("app.agents.chart_agent.get_gemini_client", return_value=_fake_gemini_client('{"charts": []}'))

    charts, errors = ChartAgent().extract([_claim("A claim with no comparable numbers.")])

    assert charts == []
    assert errors == []


def test_mismatched_labels_and_values_are_dropped(mocker):
    mocker.patch(
        "app.agents.chart_agent.get_gemini_client",
        return_value=_fake_gemini_client(
            '{"charts": ['
            '{"title": "Bad chart", "labels": ["A", "B", "C"], "values": [1, 2]}, '
            '{"title": "Good chart", "labels": ["X", "Y"], "values": [3, 4]}'
            "]}"
        ),
    )

    charts, errors = ChartAgent().extract([_claim("Some claim.")])

    assert errors == []
    assert len(charts) == 1
    assert charts[0].title == "Good chart"


def test_chart_with_no_labels_is_dropped(mocker):
    mocker.patch(
        "app.agents.chart_agent.get_gemini_client",
        return_value=_fake_gemini_client('{"charts": [{"title": "Empty", "labels": [], "values": []}]}'),
    )

    charts, errors = ChartAgent().extract([_claim("Some claim.")])

    assert charts == []
    assert errors == []


def test_chart_agent_retries_a_transient_rate_limit_then_succeeds(mocker):
    mocker.patch("app.retry.time.sleep")  # skip real backoff delays

    class _FakeAPIError(Exception):
        def __init__(self, code):
            self.code = code

    client = MagicMock()
    client.models.generate_content.side_effect = [
        _FakeAPIError(429),
        MagicMock(text='{"charts": [{"title": "Recovered chart", "labels": ["A"], "values": [1.0]}]}'),
    ]
    mocker.patch("app.agents.chart_agent.get_gemini_client", return_value=client)

    charts, errors = ChartAgent().extract([_claim("Some claim.")])

    assert errors == []
    assert len(charts) == 1
    assert charts[0].title == "Recovered chart"
    assert client.models.generate_content.call_count == 2
