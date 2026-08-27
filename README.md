# Aurelia — Deep Research Studio

A multi-agent research system that plans a question, searches the open web and
academic literature, fact-checks its own claims, and writes a cited report you
can trace line by line — with a live, Perplexity-style frontend that shows the
nine pipeline stages running in real time.

Every dependency and service used here sits inside a genuinely free tier. No
paid APIs, no credit card.

> **Build status.** All phases in the plan (0–14) are implemented. This
> repository was authored and statically reviewed in an environment that can't
> reach the live APIs, so nothing here has been run for you — the code is
> written and self-consistent, but *you* run it. Setup and run commands live in
> [`SETUP_AND_RUN.md`](SETUP_AND_RUN.md); this README is the map.

---

## What it does

You ask a research question. A LangGraph pipeline of specialized agents takes
it from there:

1. A **Planner** breaks the question into focused sub-questions.
2. **Retrieval agents** gather sources in parallel from the web (Exa, Serper,
   or keyless DuckDuckGo — whichever is configured), Wikipedia, and the
   academic literature (arXiv, Semantic Scholar, OpenAlex,
   PubMed/Europe PMC, Crossref).
3. A **dedupe-and-rank** stage collapses duplicates and orders by relevance
   using local embeddings (FAISS) — no API cost.
4. A **Fact Checker** cross-references each claim against the sources and
   attaches a verdict (supported / contradicted) and a confidence level.
5. A **Writer** drafts the report from *verified* claims with inline `[n]`
   citations; a **Reviewer** critiques it and can send it back for revision.
6. A **Citation Generator** compiles the bibliography (APA or MLA), and a
   **Chart Generator** extracts genuinely chartable numeric data.

The frontend streams all of this over Server-Sent Events: a live agent tracker,
a report whose every `[n]` marker links to its source, tabbed web/paper source
cards, contradiction badges, interactive charts, and a PDF export.

For a walkthrough written for someone *using* the app, see
[`docs/USER_GUIDE.md`](docs/USER_GUIDE.md). For how it's built, see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Repository layout

```
app/                 FastAPI backend + the LangGraph pipeline
  main.py            API: /health, /research, /research/stream, /research/pdf, /library/*
  graph.py           the 9-stage pipeline (incl. the writer↔reviewer revision loop)
  schemas.py         Document / ResearchPlan / VerifiedClaim / ChartSpec / …
  model_router.py    Gemini (heavy) + Groq (light) routing with cross-provider fallback
  cache.py           env-driven retrieval cache (sqlite | postgres | redis), fail-open
  rate_limit.py      optional per-user/IP daily quotas (DB-backed)
  citations.py       numbered source index + APA/MLA formatting
  stream_events.py   stage labels, human-readable summaries, SSE framing
  agents/            planner, search, paper_retrieval, wikipedia, openalex, pubmed,
                     crossref, fact_checker, writer, reviewer, chart
  db/                SQLAlchemy models + session (SQLite locally, Postgres in prod)
  routers/library.py saved-library CRUD (auth-scoped)
web/                 Next.js 14 frontend (the current UI) — see web/README.md
frontend/            legacy Vite prototype (Phases 1–5); superseded by web/, kept for reference
scripts/             run_pipeline.py · smoke_test_graph.py · load_sanity.py
migrations/          Alembic migrations (Postgres)
supabase/schema.sql  Row-Level-Security policies for the saved library
tests/               backend test suite (pytest)
```

Documentation index: [`SETUP_AND_RUN.md`](SETUP_AND_RUN.md) (from-scratch setup)
· [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) · [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
· [`DEPLOY.md`](DEPLOY.md) · [`PHASES.md`](PHASES.md) · [`DESIGN.md`](DESIGN.md).

---

## Quick start

Requires **Python 3.11+** and **Node 18.18+** (20+ recommended). All commands
run from the repo root unless noted.

```bash
# Terminal 1 — backend (http://localhost:8000)
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # then add your free keys (see below)
uvicorn app.main:app --reload

# Terminal 2 — frontend (http://localhost:3000)
cd web
npm install
cp .env.example .env.local         # optional; defaults assume the backend on :8000
npm run dev
```

Open http://localhost:3000. The app is **anonymous-first**: with only the two
required keys below it runs end to end. Sign-in and the saved library are
optional and light up only when Supabase credentials are present.

The full, step-by-step version (virtualenv, migrations, Docker, and what each
command should print) is in [`SETUP_AND_RUN.md`](SETUP_AND_RUN.md).

---

## Configuration

### Backend keys (repo-root `.env`)

A Gemini key is required; a web-search key (Exa or Serper) is strongly
recommended. Everything else has a safe default — including web search, which
falls back to keyless DuckDuckGo if you set no search key at all.

| Key | Required? | Get it at | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | **Yes** | aistudio.google.com/apikey | Free, no card. Powers every reasoning stage. |
| `EXA_API_KEY` | Recommended | exa.ai | Free tier: recurring monthly credit, no card. Primary web search. |
| `SERPER_API_KEY` | Recommended | serper.dev | Free tier: ~2,500 lookups, no card. Tried after Exa. |
| `SEARCH_PROVIDER` | Optional | — | `auto` (default) tries Exa → Serper → DuckDuckGo. Or force an order, e.g. `serper,duckduckgo`. |
| `GROQ_API_KEY` | Recommended | console.groq.com/keys | Free, no card. Speeds up the "light" stages when routing is on. |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional | semanticscholar.org/product/api | Works without; a free key gives a higher rate limit. |
| `DATABASE_URL` | Optional | — | Defaults to local SQLite. Point at Supabase Postgres in prod. |
| `ALLOWED_ORIGINS` | Optional | — | CORS allow-list; defaults to `http://localhost:3000`. |
| `RATE_LIMIT_ENABLED` | Optional | — | Off by default; turn on for shared deployments. |
| `SUPABASE_JWT_SECRET` / `SUPABASE_URL` | Optional | Supabase project | Enables the backend to *recognize* signed-in users. |

DuckDuckGo web search, arXiv, Wikipedia, OpenAlex, PubMed (Europe PMC), and
Crossref need **no key** (Tavily still works if you set `TAVILY_API_KEY`, but
it's optional now that its free tier asks for a card).
Local embedding models download once from Hugging Face on first run, then run
fully offline. The complete annotated list is in `.env.example` and
[`app/config.py`](app/config.py).

### Frontend env (`web/.env.local`)

All optional — the app has working defaults.

| Key | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Where the backend lives. |
| `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` | *(blank)* | Enable sign-in + saved library. |
| `NEXT_PUBLIC_SENTRY_DSN` | *(blank)* | Optional client error reporting. |

---

## Optional: sign-in and the saved library

The app never *requires* auth; it only *recognizes* it. To turn on accounts and
the `/library` page:

1. Create a free project at supabase.com.
2. Run [`supabase/schema.sql`](supabase/schema.sql) in the Supabase SQL editor
   (creates the tables and their Row-Level-Security policies).
3. Put the project URL + anon key into `web/.env.local`.
4. Optionally set `SUPABASE_JWT_SECRET` (and `DATABASE_URL` for Postgres) in the
   repo-root `.env` so the backend attributes saved runs to the signed-in user.

Row-Level Security means each user only ever sees their own saved reports — the
database enforces it, not the frontend.

---

## Testing

```bash
# Backend
pytest -q

# Frontend (from web/)
npm run test          # Vitest unit/component tests
npm run test:e2e      # Playwright end-to-end (mocked backend, fully offline)
```

The backend suite runs with **zero API keys** configured (all external calls are
faked). The Playwright specs intercept every backend call, so they need no keys
and no running API. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#testing)
for what's covered.

A load-sanity probe for concurrent behavior against a *running* backend:

```bash
python -m scripts.load_sanity -n 3
```

---

## Deployment

Free-tier deployment is documented end to end in [`DEPLOY.md`](DEPLOY.md):
backend as a Docker image on Hugging Face Spaces (or Render/Fly), frontend on
Vercel (root directory `web/`), Supabase Postgres for persistence, GitHub
Actions for CI, and an optional keep-warm ping to dodge cold starts.

---

## Design & free-tier philosophy

The visual identity — the reactive "Emerald Horizon" Three.js background, the
emerald + champagne palette, and the Fraunces/Geist/Newsreader type pairing — is
specified in [`DESIGN.md`](DESIGN.md).

Two principles run through the whole build: **free and no-card only** (every
service stays inside a real free tier), and **env-driven and deploy-ready** (no
hard-coded URLs or secrets; local↔prod is a config flip). The retrieval layer is
cached and retried with backoff so a repeated question doesn't spend quota
twice, and every agent degrades gracefully — a source outage or a rate limit
shows up as a note in the report, never a crash.
