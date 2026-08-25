"""
Chart Agent — looks across all verified claims for genuinely comparable
numeric data (e.g. different sources reporting different values for the
same measure) and extracts it into a chartable structure.

Narrow by design, like the Fact Checker: the LLM's only job is to spot and
pull out numbers already present in the claims — it never computes,
estimates, or invents a value. chart_render.py then draws exactly the
numbers/labels it returns, nothing added in between. If nothing in the
claims is genuinely chart-worthy, it returns an empty list; a report with
no chart is far better than a report with a fabricated one.
"""

from google.genai import types
from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm_clients import get_gemini_client
from app.retry import call_with_backoff, is_retryable_http_error
from app.schemas import ChartSpec, VerifiedClaim

CHART_EXTRACTION_PROMPT = """You are looking for genuinely chart-worthy numeric comparisons in the verified claims below — for example, different sources reporting different numeric values for the same measure, or a claim listing several related quantities that are naturally compared side by side.

Extract each one as a chart: a short title, an x_label and y_label (put units in y_label, e.g. "hours" or "percent"), a list of labels (what each bar/point represents — e.g. source names or categories), and a matching list of numeric values with NO units attached to the numbers themselves.

Only extract genuine, already-stated numbers from the claims below — never estimate, round meaningfully, or invent a value that isn't explicitly present. If nothing here is genuinely chart-worthy, return an empty list. A report with no chart is better than a report with a fabricated one.

Verified claims:
{claims_text}
"""


class _ChartExtractionOutput(BaseModel):
    charts: list[ChartSpec] = Field(default_factory=list)


def _format_claims(verified_claims: list[VerifiedClaim]) -> str:
    if not verified_claims:
        return "(no verified claims)"
    return "\n".join(f"- [{claim.sub_question}] {claim.text}" for claim in verified_claims)


class ChartAgent:
    def __init__(self):
        self.settings = get_settings()

    def extract(self, verified_claims: list[VerifiedClaim]) -> tuple[list[ChartSpec], list[str]]:
        """Returns (chart_specs, errors). An empty list is a normal,
        expected outcome — most research questions won't have chartable
        numeric comparisons — and it's what's returned whether nothing
        was found or the call itself failed, since there's no reasonable
        fallback to fabricate for a chart specifically."""
        if not verified_claims:
            return [], []

        client = get_gemini_client()
        if client is None:
            return [], ["GEMINI_API_KEY not configured — skipped chart extraction"]

        try:
            response = call_with_backoff(
                lambda: client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=CHART_EXTRACTION_PROMPT.format(claims_text=_format_claims(verified_claims)),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=_ChartExtractionOutput,
                    ),
                ),
                is_retryable=is_retryable_http_error,
            )
            output = _ChartExtractionOutput.model_validate_json(response.text)
        except Exception as exc:
            return [], [f"Chart extraction failed: {exc}"]

        # Defensive filter: the schema constrains types but not that labels
        # and values actually line up — drop anything malformed rather
        # than let a broken spec reach matplotlib.
        valid_charts = [chart for chart in output.charts if chart.labels and len(chart.labels) == len(chart.values)]
        return valid_charts, []
