/**
 * TypeScript mirror of the backend Pydantic schemas (app/schemas.py) and the
 * /research response shape (app/main.py :: ResearchPipelineResponse).
 *
 * Keep field names byte-for-byte identical to the backend — the SSE
 * "complete" event ships a serialized ResearchPipelineResponse and we read
 * these fields directly off it.
 */

export type SourceType =
  | "web"
  | "arxiv"
  | "semantic_scholar"
  | "openalex"
  | "pubmed"
  | "crossref"
  | "wikipedia";

export interface ResearchDocument {
  title: string;
  authors: string[];
  abstract?: string | null;
  snippet?: string | null;
  url: string;
  source: SourceType;
  published_date?: string | null;
  citation_count?: number | null;
  relevance_score?: number | null;
  raw_id?: string | null;
  sub_question?: string | null;
}

export interface SubQuestion {
  question: string;
  web_query: string;
  academic_query: string;
}

export interface ResearchPlan {
  original_query: string;
  sub_questions: SubQuestion[];
}

export type ClaimVerdict =
  | "corroborated"
  | "single_source"
  | "contradicted"
  | "unverified";

export interface VerifiedClaim {
  text: string;
  sub_question: string;
  supporting_sources: ResearchDocument[];
  contradicting_sources: ResearchDocument[];
  verdict: ClaimVerdict;
  confidence: number;
  note?: string | null;
}

export type ReviewDecision = "approve" | "revise" | "";

export type ChartType = "bar" | "line";

export interface ChartSpec {
  title: string;
  chart_type: ChartType;
  x_label: string;
  y_label: string;
  labels: string[];
  values: number[];
}

/** Full result — the payload of the SSE "complete" event and of POST /research. */
export interface ResearchResult {
  query: string;
  plan: ResearchPlan;
  web_results: ResearchDocument[];
  paper_results: ResearchDocument[];
  final_documents: ResearchDocument[];
  verified_claims: VerifiedClaim[];
  draft: string;
  review_decision: ReviewDecision;
  review_feedback: string;
  revision_count: number;
  final_report: string;
  chart_specs: ChartSpec[];
  errors: string[];
  /**
   * Set by the backend when the request was authenticated and the result was
   * auto-saved to the caller's library (Phase 11). Absent for anonymous runs.
   */
  saved_id?: string | null;
}

/** Request body for /research, /research/stream, /research/pdf. */
export interface ResearchRequest {
  query: string;
  num_sub_questions?: number;
  max_results_per_subquestion?: number;
  target_language?: string;
  max_revisions?: number;
  citation_style?: "apa" | "mla";
}

// ── SSE event shapes (app/main.py :: run_research_pipeline_stream) ──

export type CitationStyle = "apa" | "mla";

/** One pipeline node finished; STAGE_LABELS keys from app/stream_events.py. */
export type StageName =
  | "planner"
  | "search_all"
  | "retrieve_all"
  | "dedupe_and_rank"
  | "fact_check"
  | "writer"
  | "reviewer"
  | "add_citations"
  | "generate_charts";

export interface StageEvent {
  type: "stage";
  stage: StageName | string;
  label: string;
  summary: string;
  errors: string[];
}

export interface ErrorEvent {
  type: "error";
  message: string;
}

export interface CompleteEvent {
  type: "complete";
  result: ResearchResult;
}

export type ResearchStreamEvent = StageEvent | ErrorEvent | CompleteEvent;

/** Canonical pipeline order — used to render the tracker before events arrive. */
export const PIPELINE_STAGES: { stage: StageName; label: string }[] = [
  { stage: "planner", label: "Planner" },
  { stage: "search_all", label: "Web Search" },
  { stage: "retrieve_all", label: "Paper Retrieval" },
  { stage: "dedupe_and_rank", label: "Deduplication & Ranking" },
  { stage: "fact_check", label: "Fact Checking" },
  { stage: "writer", label: "Writer" },
  { stage: "reviewer", label: "Reviewer" },
  { stage: "add_citations", label: "Citation Generator" },
  { stage: "generate_charts", label: "Chart Generator" },
];
