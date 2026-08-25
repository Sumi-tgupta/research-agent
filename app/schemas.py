"""
Shared schema for anything a retrieval agent finds.

Tavily, ArXiv, and Semantic Scholar all return differently-shaped JSON.
Every agent normalizes its results into `Document` before handing them
back, so downstream agents (Fact Checker, Writer, Citation Generator in
later phases) only ever deal with one shape regardless of where a source
came from.
"""

from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    WEB = "web"
    ARXIV = "arxiv"
    SEMANTIC_SCHOLAR = "semantic_scholar"


class Document(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None          # full abstract, papers only
    snippet: str | None = None           # short excerpt, web results only
    url: str = ""
    source: SourceType
    published_date: str | None = None
    citation_count: int | None = None    # papers only
    relevance_score: float | None = None
    raw_id: str | None = None            # arxiv id / semantic scholar paperId
    sub_question: str | None = None      # which plan sub-question this came from, if any


class AgentResult(BaseModel):
    """What every agent's `.run()` returns — a uniform, testable contract."""

    query: str
    documents: list[Document] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    source_agent: str


class SubQuestion(BaseModel):
    """One facet of the research question, with queries tuned per source type."""

    question: str
    web_query: str = Field(description="Phrased the way someone would type it into a search engine")
    academic_query: str = Field(description="Phrased with formal/technical terms suited to paper search")


class ResearchPlan(BaseModel):
    original_query: str
    sub_questions: list[SubQuestion] = Field(default_factory=list)


class ClaimVerdict(str, Enum):
    CORROBORATED = "corroborated"    # 2+ independent sources agree, none disagree
    SINGLE_SOURCE = "single_source"   # exactly one source states this
    CONTRADICTED = "contradicted"      # at least one source disagrees
    UNVERIFIED = "unverified"          # no source could be confidently attributed


class VerifiedClaim(BaseModel):
    """One factual claim plus which retrieved sources support or contradict
    it. `verdict` and `confidence` are derived in plain Python from source
    counts (see agents/fact_checker_agent.py), not self-reported by the LLM —
    that's the one part of this phase we don't ask the model to judge."""

    text: str
    sub_question: str
    supporting_sources: list[Document] = Field(default_factory=list)
    contradicting_sources: list[Document] = Field(default_factory=list)
    verdict: ClaimVerdict
    confidence: float
    note: str | None = None


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"


class ReviewResult(BaseModel):
    decision: ReviewDecision
    feedback: str = ""


class ChartSpec(BaseModel):
    """A single chartable comparison extracted from verified claims —
    e.g. different sources reporting different values for the same
    measure. `labels` and `values` must be the same length."""

    title: str
    chart_type: str = "bar"   # "bar" or "line"
    x_label: str = ""
    y_label: str = ""
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
