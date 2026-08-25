# Multi-Agent Research System — Phase 0 through 7 (complete)

Status: **all seven phases done.** Setup, retrieval, Planner/orchestration,
fact-checking, Writer/Reviewer, citations/PDF/charts, streaming + React
frontend, and now hardening — retry/backoff, caching, a top-level safety
net, and guidance for testing this against real research questions.

## Quick start (backend + frontend together)

```bash
# Terminal 1 — backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your free keys, see below
uvicorn app.main:app --reload

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## What's here

```
app/
  config.py                       # loads every key/default from .env
  schemas.py                      # Document / ResearchPlan / VerifiedClaim / ReviewResult / ChartSpec
  llm_clients.py                  # Gemini + Groq client setup (Groq still unused)
  vector_store.py                  # FAISS + local embeddings — dedup & relevance ranking (Phase 2)
  retrieval_index.py                # LlamaIndex + FAISS — supplementary excerpts for the Writer (Phase 4)
  citations.py                       # numbered source index, APA/MLA formatting, References section (Phase 5)
  chart_render.py                    # matplotlib — renders ChartSpec -> PNG (Phase 5)
  pdf_export.py                      # ReportLab — renders the final report (+ charts) -> PDF (Phase 5)
  stream_events.py                    # stage labels, human-readable summaries, SSE formatting (Phase 6)
  retry.py                             # exponential backoff, centralized retry classification (Phase 7)
  cache.py                              # SQLite-backed TTL cache for retrieval calls (Phase 7)
  graph.py                          # the real pipeline (LangGraph), 9 stages incl. the revision loop
  agents/
    search_agent.py                  # Tavily web search — now cached + retried
    paper_retrieval_agent.py         # ArXiv + Semantic Scholar — now cached + (Semantic Scholar) retried
    planner_agent.py                  # Gemini-powered query -> sub-questions — now retried
    fact_checker_agent.py              # cross-references sources per sub-question — now retried
    writer_agent.py                     # drafts the report from verified claims, with [N] citations — now retried
    reviewer_agent.py                    # critiques the draft, approve/revise — now retried
    chart_agent.py                        # extracts genuinely chartable numeric data from claims — now retried
  main.py                          # FastAPI app — agent endpoints, /research, /research/stream, /research/pdf
frontend/                          # React (Vite) — see frontend/README.md
scripts/
  smoke_test_graph.py               # Phase 1: proves Search + Paper agents work as LangGraph nodes
  run_pipeline.py                    # live end-to-end run — now also demos the cache directly
tests/                              # 153 tests total, see Testing below
```

## Setup

Requires Python 3.10+ and Node 18+.

| Key | Get it at | Notes |
|---|---|---|
| `TAVILY_API_KEY` | tavily.com | Free tier: 1,000 search credits/month |
| `SEMANTIC_SCHOLAR_API_KEY` | semanticscholar.org/product/api | Optional — a free key gives a dedicated (higher) rate limit |
| `GEMINI_API_KEY` | aistudio.google.com/apikey | Free tier, no card. Powers every LLM stage. |
| `GROQ_API_KEY` | console.groq.com/keys | Free tier, no card. **Still unused** — nothing's changed that since Phase 4's note. |

ArXiv needs no key. Local embedding models download from huggingface.co on
first run only, then are fully cached and offline.

## What Phase 7 actually changed

### Retry / backoff (`app/retry.py`)

Every retrieval and LLM call is now wrapped in `call_with_backoff` —
exponential delay with jitter, centralized in one module rather than
reimplemented per integration. The important part is *what's classified
as retryable*:

- **Retried**: a 429 (rate limited), a 5xx (transient server-side issue),
  or a network-level timeout/connection error.
- **Not retried**: a bad or missing API key, a monthly quota already
  exhausted, or a malformed request — retrying these wastes an attempt
  and cannot change the outcome. They fail immediately and fall straight
  through to each agent's existing fallback logic, unchanged.

**ArXiv is deliberately not wrapped a second time** — the `arxiv` package
already retries `HTTPError`/`ConnectionError` internally (confirmed by
reading its source: `num_retries`, default 3), and stacking another retry
loop on top would just multiply the worst-case wait time for no benefit.

Tavily needs its own retry predicate (its SDK's exceptions don't carry an
HTTP status code the way `requests` and `google-genai` do), so
`is_retryable_tavily_error` only retries Tavily's own `TimeoutError` plus
generic network errors — every one of Tavily's permanent failure modes
(bad key, quota exceeded, bad request, forbidden) still fails fast.

### Caching (`app/cache.py`)

A SQLite-backed cache (stdlib `sqlite3`, no extra dependency), scoped
**only** to the retrieval agents — Tavily, ArXiv, and Semantic Scholar.
Each source is cached separately by `(namespace, query, max_results)`, so
a cache hit on one source doesn't block a fresh attempt on another. TTL
defaults to 1 week; delete `.cache/` to reset it.

The LLM reasoning agents (Planner, Fact Checker, Writer, Reviewer, Chart
Agent) are **deliberately not cached** — the project plan's own phrasing,
"avoid re-querying same sources," is specifically about the retrieval
layer. Caching "what the Planner said last time" would quietly serve
stale reasoning instead of a genuine rate-limit optimization, and would
undermine the revision loop, which depends on the Writer/Reviewer
actually reconsidering things each pass.

### Top-level safety net (`app/main.py`)

Every agent already has its own fallback logic for its own external
calls. This adds one more layer underneath all of that: if something
genuinely unanticipated breaks deeper in the graph (verified with a test
that injects a bug into `add_citations_node`, which has no try/except of
its own at all), `/research` still returns a valid response instead of a
raw 500, and `/research/stream` still sends a `complete` event with
whatever partial state was accumulated — so the frontend is never left
stuck on "running" with nothing to show.

## Testing this against real research questions

This is the one thing every phase's README has had to defer — I can
verify code correctness and resilience from this build sandbox, but not
whether the *live* services and *live* model output are actually good on
a real question. Once you have real keys:

```bash
python -m scripts.run_pipeline "your research question"
```

This now also demonstrates caching directly: it runs the same search
twice via `SearchAgent`/`PaperRetrievalAgent` before the full pipeline,
timed both times — the second call should be close to instant, served
from `.cache/` instead of spending Tavily/Semantic Scholar quota again.

A few suggested test questions, chosen for having genuine multi-source
agreement *and* disagreement to check the Fact Checker's contradiction
handling, not just its happy path:

- "What is caffeine's elimination half-life in healthy adults?" (sources
  commonly disagree — a good check that contradictions get surfaced, not
  silently resolved)
- "What are the health effects of intermittent fasting?" (mix of strong
  and contested evidence — checks that confidence levels actually vary
  across claims, not uniformly high)
- "What is the current scientific consensus on microplastics in drinking
  water?" (broad enough to need real sub-question decomposition)

What to actually check when you run these:
- Do the sub-questions in the Planner's output actually make sense for
  the topic?
- Does the Fact Checker's `contradicted` verdict fire on a question where
  sources plausibly disagree, and does the final report actually mention
  the disagreement rather than picking a side?
- Does a second identical run finish noticeably faster (cache working)?
- Does the PDF look right — headings, bullets, citations resolving to
  the correct source, chart embedded if one was extracted?

## Testing (automated)

```bash
pytest tests/ -v
```

153 tests, all runnable with zero API keys configured. New this phase:

- **`test_retry.py` (16 tests)** — the backoff engine itself, using an
  injected fake `sleep` so retry-count/delay assertions run instantly
  instead of waiting through real backoff.
- **`test_cache.py` (12 tests)** — real SQLite operations against temp
  files: roundtrips, TTL expiry, key stability, and the default-cache
  singleton (also found and fixed a real bug along the way: `Cache`'s
  `path` default was bound at class-definition time rather than looked
  up dynamically, the same class of bug as `retry.py`'s `sleep` default —
  meaning redirecting `DEFAULT_CACHE_PATH` after import silently
  wouldn't have worked without this fix).
- **Cache-hit and retry tests added to every retrieval/LLM agent's own
  test file** (e.g. `test_agents.py`, `test_planner.py`,
  `test_fact_checker.py`) — proving a repeated query is actually served
  from cache without a second network call, and a transient failure is
  actually retried and recovers, not just that the code compiles.
- **Two new safety-net tests in `test_main_endpoints.py`** — inject an
  unanticipated crash into a node with no try/except of its own, confirm
  `/research` and `/research/stream` both degrade gracefully instead of
  raising.

Every test file that constructs a `SearchAgent`/`PaperRetrievalAgent` now
uses an `isolated_cache` fixture (`tests/conftest.py`) pointed at a temp
file — without it, a cached result from one test (or a previous run
entirely, since the cache is a real file on disk) could silently satisfy
a later test's assertions without the mocked API call actually being
exercised that time. This was a real bug I caught mid-phase, not a
hypothetical.

## Free-tier notes (cumulative)

- **Tavily**: `search_depth="basic"` (1 credit vs. 2 for `"advanced"`);
  cached; retried only on timeout.
- **ArXiv**: 3-second delay between requests (its own library handles
  this and its own retries); cached.
- **Semantic Scholar**: cached; retried on 429/5xx; a persistent 429 still
  gives the "add an API key" message, now specifically after retries were
  already exhausted.
- **Gemini**: defaults to `gemini-2.5-flash`; every call retried on
  429/5xx; ~10 calls per full run (Planner, one per sub-question for Fact
  Checker, 1-2 Writer, 1-2 Reviewer, 1 Chart Agent).
- **CORS is wide open** (`allow_origins=["*"]`) — tighten before deploying
  anywhere public.
- **What's still not done**: true concurrent-request handling (this
  project assumes one research session at a time — a second concurrent
  `/research/stream` call would work but wouldn't get any special
  coordination), and a cache eviction/size cap (TTL-based expiry only,
  no hard size limit — fine for personal use, would need attention
  before any shared/production deployment).

## Project status

All 7 phases from the original plan are built, tested, and — within the
limits of a sandbox that can't reach any of the real APIs — verified as
thoroughly as possible without live keys. The remaining gap, everywhere,
is the same one: running it for real, on real questions, with real keys.
That's now genuinely the next step, not another phase.
#   r e s e a r c h - a g e n t  
 