"""
Proves search_agent_node / paper_retrieval_node slot into a real LangGraph
StateGraph. This is a smoke test, not Phase 2's orchestration — there's no
Planner and the two nodes just run in sequence with no branching logic.

Since it makes live calls, set a web-search key — EXA_API_KEY or
SERPER_API_KEY (and ideally SEMANTIC_SCHOLAR_API_KEY) — in .env; with none
set it still runs via keyless DuckDuckGo. Run from the project root:

    python -m scripts.smoke_test_graph "your query here"
"""

import sys
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.paper_retrieval_agent import paper_retrieval_node
from app.agents.search_agent import search_agent_node
from app.schemas import Document


class ResearchState(TypedDict, total=False):
    query: str
    max_web_results: int
    max_paper_results: int
    web_results: list[Document]
    paper_results: list[Document]
    errors: list[str]


def build_graph():
    graph = StateGraph(ResearchState)
    graph.add_node("search_agent", search_agent_node)
    graph.add_node("paper_retrieval_agent", paper_retrieval_node)
    graph.add_edge(START, "search_agent")
    graph.add_edge("search_agent", "paper_retrieval_agent")
    graph.add_edge("paper_retrieval_agent", END)
    return graph.compile()


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "retrieval augmented generation"
    app = build_graph()
    result = app.invoke({"query": query, "max_web_results": 3, "max_paper_results": 3})

    print(f"Query: {query}\n")
    print(f"Web results: {len(result.get('web_results', []))}")
    print(f"Paper results: {len(result.get('paper_results', []))}")
    if result.get("errors"):
        print("\nErrors:")
        for err in result["errors"]:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
