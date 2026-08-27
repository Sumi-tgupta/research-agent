import type { Page } from "@playwright/test";

/**
 * Offline backend doubles for E2E. The real FastAPI service is never contacted;
 * we intercept its routes and return canned responses so the frontend flow can
 * be exercised deterministically.
 */

/** A full ResearchResult shaped like the SSE "complete" payload (app/main.py). */
export function buildResult(query: string, finalReport: string) {
  return {
    query,
    plan: { original_query: query, sub_questions: [] },
    web_results: [],
    paper_results: [],
    final_documents: [],
    verified_claims: [],
    draft: finalReport,
    review_decision: "approve",
    review_feedback: "",
    revision_count: 0,
    final_report: finalReport,
    chart_specs: [],
    errors: [],
  };
}

/** Serialize a short pipeline run as an SSE stream (two stages + complete). */
export function sseBody(query: string, finalReport: string): string {
  const events = [
    {
      type: "stage",
      stage: "planner",
      label: "Planner",
      summary: "Planned the query",
      errors: [],
    },
    {
      type: "stage",
      stage: "search_all",
      label: "Web Search",
      summary: "Gathered sources",
      errors: [],
    },
    { type: "complete", result: buildResult(query, finalReport) },
  ];
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
}

/** Intercept /health and /research/stream for the given page. */
export async function mockBackend(
  page: Page,
  opts: { query: string; report: string }
): Promise<void> {
  await page.route("**/health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        phases_complete: [0, 1, 2, 3, 4, 5, 6],
      }),
    })
  );

  await page.route("**/research/stream", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "cache-control": "no-cache" },
      body: sseBody(opts.query, opts.report),
    })
  );
}
