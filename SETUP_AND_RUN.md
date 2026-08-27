# Setup & Run — the whole codebase, from scratch

This is the complete, from-scratch guide to installing and running **everything**
in this repository — backend, frontend, database, tests, and the optional
extras — covering all build phases (0–14).

> ## ⚠️ Nothing here was run for you
> Per the project instruction, I only **wrote and statically reviewed** the
> code. I did **not** execute `pip install`, `pytest`, `uvicorn`, `npm install`,
> `npm run dev/build/lint/test`, `npx playwright`, `alembic`, or `docker`. Every
> command below is for **you** to run and verify on your machine. Where I say
> "you should see …", that's the expected output, not something I observed.
>
> Work through the sections in order the first time. Later, the
> [command cheat-sheet](#command-cheat-sheet) at the end is all you'll need.

All commands run from the repository root
(`D:\CODE\research-system`) unless a step says otherwise. Commands are shown for
**Windows PowerShell** (your environment) with macOS/Linux equivalents noted
where they differ.

---

## 0. Prerequisites

- **Python 3.11+** (3.13 is fine; a `.venv/` may already exist in the repo).
- **Node.js 18.18+** (20+ recommended) and **npm**.
- **Git** (to clone, if you don't already have the repo locally).
- Optional: **Docker Desktop** (only for the container build in §13).

Two free API keys are the minimum to get a *real* report (see §2). The test
suites need **no** keys at all.

Check your versions:

```powershell
python --version
node --version
npm --version
```

---

## 1. Backend — create the environment and install

From the repo root:

```powershell
# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt
```

The first install pulls ML wheels (torch, faiss-cpu, sentence-transformers) and
can take a while; they're cached afterward. This is expected, not a hang.

> If PowerShell blocks the activation script, allow it for this session:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`, then
> re-run the activate line.

---

## 2. Backend — configure keys (`.env`)

```powershell
Copy-Item .env.example .env          # macOS/Linux: cp .env.example .env
```

Open `.env` and fill in the keys. Only the first two are required for a real
run; everything else has a safe default and can stay blank.

| Key | Required? | Where to get it (all free, no card) |
|---|---|---|
| `GEMINI_API_KEY` | **Yes** | https://aistudio.google.com/apikey |
| `TAVILY_API_KEY` | **Yes** | https://tavily.com |
| `GROQ_API_KEY` | Recommended | https://console.groq.com/keys |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional | https://www.semanticscholar.org/product/api |

arXiv, Wikipedia, OpenAlex, PubMed (Europe PMC), and Crossref need no key. The
full annotated list of settings is in `.env.example` and `app/config.py`.

> **Without any keys**, the backend still starts and the test suite still passes
> (external calls are faked in tests), but a live `/research` run won't have a
> search provider or an LLM to call.

---

## 3. Backend — run the API and verify it

```powershell
uvicorn app.main:app --reload
```

This serves the API at **http://localhost:8000**. In a **second** terminal,
confirm it's alive:

```powershell
curl http://localhost:8000/health
# Expected: {"status":"ok","phases_complete":[0,1,2,3,4,5,6]}
```

Leave this backend terminal running — the frontend talks to it.

---

## 4. Backend — run the test suite

The backend tests run with **zero API keys** configured; all external calls are
mocked.

```powershell
pytest -q
```

You should see the suite pass. It covers each agent (including cache-hit and
retry paths), the LangGraph pipeline, citations, PDF/chart rendering, SSE event
shaping, the cache backends, the library/status helpers, and the graceful-
degradation safety net. `redis` and `sentry-sdk` are optional and intentionally
not required for the suite.

---

## 5. Frontend — install

In a **new** terminal (keep the backend running), from the repo root:

```powershell
cd web
npm install
```

> There's no committed `package-lock.json`, so use `npm install` (not `npm ci`).
> This also installs the Phase-14 test/dev dependencies (Vitest, Playwright,
> Testing Library, the bundle analyzer).

---

## 6. Frontend — configure env (optional)

The frontend works with no configuration (it assumes the backend at
`http://localhost:8000`). To customize:

```powershell
Copy-Item .env.example .env.local    # macOS/Linux: cp .env.example .env.local
```

| Key | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend location. |
| `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` | *(blank)* | Turn on sign-in + saved library (§11). |
| `NEXT_PUBLIC_SENTRY_DSN` | *(blank)* | Optional client error reporting (§14). |

---

## 7. Frontend — run it

```powershell
npm run dev
```

Open **http://localhost:3000**. Ask a question (or click an example chip) and
you should see the live agent tracker run and a cited report stream in. This is
the full experience — see [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) for a tour.

---

## 8. Frontend — run the tests

From `web/`:

```powershell
# Unit + component tests (Vitest) — no backend or keys needed
npm run test

# End-to-end tests (Playwright) — fully offline, backend is mocked
npx playwright install chromium     # one-time: download the browser
npm run test:e2e
```

The Vitest suite covers the SSE client, the citation logic, the research-state
reducer, the horizon store, and the charts panel. The Playwright specs drive the
landing page, a full research flow, and the library page, intercepting every
backend call — so they need no keys and no running API.

Other frontend scripts (these mirror what CI checks):

```powershell
npm run lint        # eslint
npm run build       # production build + type-check
npm run start       # serve the production build (after build)
```

---

## 9. Your first real research run

With real keys in `.env`, two ways to exercise the full pipeline:

**In the UI** — just ask a question at http://localhost:3000.

**From the command line** (backend venv active, from repo root):

```powershell
python -m scripts.run_pipeline "What is caffeine's elimination half-life in healthy adults?"
```

This prints the plan, per-source counts, verified claims, the review decision,
and the final report. It also demonstrates the retrieval cache by running the
same search twice — the second pass should be near-instant.

Good first questions (chosen to exercise multi-source agreement *and*
disagreement, so the Fact Checker's contradiction handling gets tested, not just
its happy path):

- "What is caffeine's elimination half-life in healthy adults?"
- "What are the health effects of intermittent fasting?"
- "What is the current scientific consensus on microplastics in drinking water?"

---

## 10. Free-tier load sanity (optional)

With the backend running, fire a few concurrent runs and see how it behaves:

```powershell
python -m scripts.load_sanity -n 3
```

It reports time-to-first-event, total duration per request, and how many
requests were cleanly rate-limited (a `429` is treated as expected graceful
degradation, not a failure). Keep the concurrency modest — each run spends real
free-tier LLM and search quota. Run `python -m scripts.load_sanity --help` for
flags.

---

## 11. Optional — accounts and the saved library (Supabase)

The app is fully functional anonymously. To enable sign-in and the `/library`
page:

1. Create a free project at https://supabase.com.
2. In the Supabase **SQL Editor**, run the contents of
   [`supabase/schema.sql`](supabase/schema.sql). This creates the library tables
   and their Row-Level-Security policies (each user sees only their own rows).
3. Put the project URL and **anon** key into `web/.env.local`
   (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`).
4. Optionally, so the backend *recognizes* signed-in callers, set in the
   repo-root `.env`:
   - `SUPABASE_JWT_SECRET` (Supabase → Project Settings → API → JWT Secret),
   - `SUPABASE_URL`,
   - and, to store data in Postgres instead of local SQLite, `DATABASE_URL`.

**Database migrations.** Local SQLite auto-creates its tables on startup — no
migration step. For Postgres (Supabase), apply the versioned migrations:

```powershell
$env:DATABASE_URL = "postgresql+pg8000://postgres:PASSWORD@db.YOUR_REF.supabase.co:5432/postgres"
alembic upgrade head
```

(macOS/Linux: `export DATABASE_URL="postgresql+pg8000://..."` then
`alembic upgrade head`.) Revisions: `0001_phase11_library`,
`0002_phase12_usage_counters`. Full detail is in [`DEPLOY.md`](DEPLOY.md) §1.

The backend never *requires* auth — anonymous requests keep working whether or
not any of this is configured.

---

## 12. Optional — production build & bundle analysis

```powershell
cd web
npm run build        # production build + type-check
npm run start        # serve it at http://localhost:3000
```

To inspect bundle sizes (opens treemaps in your browser):

```powershell
# PowerShell
$env:ANALYZE = "true"; npm run build; Remove-Item Env:\ANALYZE
# macOS/Linux: ANALYZE=true npm run build
```

---

## 13. Optional — Docker (backend) and deployment

The Dockerfile builds the **backend only** (`web/` and `frontend/` are excluded
via `.dockerignore`):

```powershell
docker build -t aurelia-api .
docker run --rm -p 8000:8000 --env-file .env aurelia-api
curl http://localhost:8000/health
```

For a Hugging Face Spaces-style port: `docker run --rm -p 7860:7860 -e PORT=7860
--env-file .env aurelia-api`.

Full free-tier hosting steps — backend on Hugging Face Spaces/Render, frontend on
Vercel (set the project **Root Directory** to `web/`), Supabase Postgres, GitHub
Actions CI, and a keep-warm ping — are in [`DEPLOY.md`](DEPLOY.md). CI is defined
in `.github/workflows/ci.yml` (a backend `pytest` job and a frontend
`lint + build` job; it does not deploy).

---

## 14. Optional — Sentry error monitoring

**Backend:** uncomment `sentry-sdk` in `requirements.txt`, `pip install` it, then
set `SENTRY_DSN` (+ optionally `APP_ENV`, `SENTRY_TRACES_SAMPLE_RATE`) in `.env`.
A blank DSN is a complete no-op, so this is entirely opt-in.

**Frontend:** set `NEXT_PUBLIC_SENTRY_DSN` in `web/.env.local`. This uses a
built-in, dependency-free reporter — no npm package required.

---

## What "working" looks like (Phase-14 quality bar)

- `pytest -q` passes with no keys configured.
- `npm run test` and `npm run test:e2e` pass (Playwright browser installed).
- `npm run build` completes with no type errors.
- Asking a question streams a live tracker and a cited report; `[n]` citations
  resolve to real sources; the PDF export opens with citations and any charts.
- Keyboard: Tab from the top reveals a "Skip to content" link; focus rings are
  visible; "reduce motion" disables the background animation.
- On deployments with limits on, exceeding the quota returns a friendly message,
  not a crash.

---

## Troubleshooting

- **`uvicorn` not found / imports fail** — the virtualenv isn't active. Re-run
  the activate line from §1 (you'll see `(.venv)` in the prompt).
- **PowerShell won't run the activate script** — see the note in §1.
- **Header shows "backend offline"** — the API isn't reachable at
  `NEXT_PUBLIC_API_BASE_URL`. Start it (§3); the UI reconnects on its own.
- **`npm run test:e2e` can't launch a browser** — run
  `npx playwright install chromium` first (§8).
- **First backend run is slow / downloads a model** — expected: the local
  embedding model downloads once from Hugging Face, then runs offline.
- **A source shows an error note in the report** — that source was down or
  rate-limited; the run continues on the others by design. A persistent Semantic
  Scholar `429` is the cue to add its (free) API key.
- **CORS error in the browser** — add your frontend origin to `ALLOWED_ORIGINS`
  in `.env` (defaults already include `http://localhost:3000`).

---

## Command cheat-sheet

```powershell
# Backend (repo root, venv active)
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000
pytest -q
python -m scripts.run_pipeline "your question"
python -m scripts.load_sanity -n 3

# Frontend (from web/)
npm install
npm run dev                            # http://localhost:3000
npm run test
npx playwright install chromium
npm run test:e2e
npm run build
```

---

## How this maps to the build phases

Phases 0–7 are the backend research pipeline (retrieval, planning, fact-check,
writer/reviewer, citations/PDF/charts, streaming, hardening) — exercised by §3,
§4, §9. Phases 8–9 are the Next.js frontend and the Perplexity-style experience —
§5–§7. Phase 10 is auth, Phase 11 persistence/library — §11. Phase 12 is backend
hardening (more sources, model routing, rate limiting, cache backends). Phase 13
is deploy/CI — §12, §13. Phase 14 is QA, accessibility, and docs — §4, §8, §10,
and this guide. The phase plan itself is in [`PHASES.md`](PHASES.md).
