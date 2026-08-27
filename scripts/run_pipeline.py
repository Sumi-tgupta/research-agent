"""
Live end-to-end run of the full pipeline:

    planner -> search_all -> retrieve_all -> dedupe_and_rank -> fact_check
        -> writer <-> reviewer -> add_citations -> generate_charts

Needs real keys in .env (GEMINI_API_KEY for the Planner/Fact Checker/
Writer/Reviewer/Chart Agent; a web-search key — EXA_API_KEY or
SERPER_API_KEY — and/or SEMANTIC_SCHOLAR_API_KEY for retrieval, though web
search falls back to keyless DuckDuckGo), plus internet access to download
the embedding model on first run (~80MB, cached locally after that — see
app/vector_store.py). Run from the project root:

    python -m scripts.run_pipeline "your research question"

Also demonstrates Phase 7's caching layer directly: the same search is run
twice against SearchAgent/PaperRetrievalAgent before the full pipeline,
timed both times, so you can see the second call being served from the
local cache instead of spending web-search/Semantic Scholar quota on an
identical repeat query.
"""

import sys
import time

from app.agents.paper_retrieval_agent import PaperRetrievalAgent
from app.agents.search_agent import SearchAgent
from app.graph import build_research_graph


def _demo_caching(query: str) -> None:
    print("--- Cache demo: running the same search twice ---")
    search_agent = SearchAgent()
    paper_agent = PaperRetrievalAgent()

    start = time.monotonic()
    search_agent.run(query, max_results=5)
    paper_agent.run(query, max_results=5)
    first_elapsed = time.monotonic() - start

    start = time.monotonic()
    search_agent.run(query, max_results=5)
    paper_agent.run(query, max_results=5)
    second_elapsed = time.monotonic() - start

    print(f"First call:  {first_elapsed:.2f}s (hit web search/ArXiv/Semantic Scholar)")
    print(f"Second call: {second_elapsed:.2f}s (should be near-instant — served from .cache/)")
    print()


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "impact of microplastics on marine food webs"

    _demo_caching(query)

    print(f"--- Full pipeline run ---")
    print(f"Query: {query}\n")

    graph = build_research_graph()
    start = time.monotonic()
    result = graph.invoke({"query": query, "num_sub_questions": 4, "max_results_per_subquestion": 5})
    elapsed = time.monotonic() - start

    plan = result["plan"]
    print(f"Plan ({len(plan.sub_questions)} sub-questions), completed in {elapsed:.1f}s:")
    for i, sub_q in enumerate(plan.sub_questions, 1):
        print(f"  {i}. {sub_q.question}")

    print(f"\nRaw web results:          {len(result.get('web_results', []))}")
    print(f"Raw paper results:        {len(result.get('paper_results', []))}")
    print(f"Final (deduped + ranked): {len(result.get('final_documents', []))}")
    print(f"Verified claims:          {len(result.get('verified_claims', []))}")
    print(f"Review:                   {result.get('review_decision', '?')} "
          f"(after {result.get('revision_count', 0)} pass(es))")
    print(f"Charts extracted:         {len(result.get('chart_specs', []))}")

    print("\n--- Final report ---\n")
    print(result.get("final_report") or result.get("draft") or "(no draft produced)")

    if result.get("errors"):
        print("\n--- Errors along the way ---")
        for err in result["errors"]:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
