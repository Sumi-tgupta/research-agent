# Running & verifying Phases 11–13

Exact commands for **you** to run. Phases 11–13 added persistence (SQLAlchemy +
Alembic + user-scoped library), Phase-12 upgrades (new free sources, model
routing, rate limiting, env-driven cache, job status), and Phase-13 deployment
plumbing (Dockerfile, Vercel config, GitHub Actions CI, optional Sentry).

> ### ⚠️ Nothing here was executed for me — or by me.
> Per your instructions, I only **wrote and statically reviewed** code. I did
> **not** run `pytest`, `uvicorn`, `alembic`, `npm install`, `npm run
> lint/build`, or `docker build`. The commands below are for you to run and
> verify. Treat any expected output as "what it should print," not "what I
> observed."

All commands run from the repo root (`D:\CODE\research-system`) unless noted.

---

## 0. Prerequisites

- Python 3.13 (a `.venv` already exists in the repo).
- Node.js 20+ and npm (for the `web/` frontend).
- Optional: Docker Desktop (for the container build in §5).

Activate the virtualenv first (Windows PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## 1. Backend — install & run tests

```powershell
pip install -r requirements.txt
pytest -q
```

New tests added in Phases 11–12 (alongside the existing suite):

- `tests/test_cache_backends.py` — the env-driven cache factory + `PostgresCache`
  (exercised over SQLite), fail-open behavior, and the resettable singleton.
- `tests/test_library_status.py` — `save_result_for_user` terminal status, and
  `set_session_status` / `get_session_status` transitions + ownership scoping.

`redis` is **not** installed (it's optional/commented in `requirements.txt`), and
the cache-backend tests are written so they don't need it. `sentry-sdk` is also
optional — the suite runs without it because a blank `SENTRY_DSN` is a no-op.

If the ML wheels (torch / faiss-cpu / sentence-transformers) make the first
install slow, that's expected; they're cached afterward.

---

## 2. Backend — run the API locally

```powershell
uvicorn app.main:app --reload
```

Then in another terminal:

```powershell
curl http://localhost:8000/health
# expected: {"status":"ok","phases_complete":[0,1,2,3,4,5,6]}
```

With no `.env`, it runs anonymously on local SQLite. Copy `.env.example` → `.env`
and fill in keys to enable search/LLMs, and `DATABASE_URL` / Supabase / Sentry as
you like.

---

## 3. Database migrations (Phase 11)

Local SQLite auto-creates its tables on startup — **no migration step needed**.

For Postgres (e.g. Supabase), apply the versioned migrations:

```powershell
$env:DATABASE_URL = "postgresql+pg8000://postgres:PASSWORD@db.YOUR_REF.supabase.co:5432/postgres"
alembic upgrade head
```

Revisions: `0001_phase11_library`, `0002_phase12_usage_counters`
(`migrations/env.py` reads `DATABASE_URL` from the app config). For the
Supabase Row-Level-Security policies, run `supabase/schema.sql` once in the
Supabase SQL editor. Full detail: [`DEPLOY.md`](DEPLOY.md) §1.

---

## 4. Frontend (`web/`) — install, lint, build, run

```powershell
cd web
npm install
npm run dev        # dev server at http://localhost:3000
```

To reproduce what CI checks:

```powershell
npm run lint       # uses the new web/.eslintrc.json
npm run build      # production build + type-check
npm run start      # serve the production build
```

Notes:
- `web/.eslintrc.json` was **added** this round so `next lint` runs
  non-interactively (previously there was no ESLint config, which would have
  prompted/failed in CI).
- All `NEXT_PUBLIC_*` env vars have safe defaults, so the build works with no
  configuration. Set `NEXT_PUBLIC_API_BASE_URL` (and optionally Supabase / Sentry
  vars) in `web/.env.local` — see `web/.env.example`.

---

## 5. Docker image (Phase 13)

```powershell
docker build -t aurelia-api .
docker run --rm -p 8000:8000 --env-file .env aurelia-api
curl http://localhost:8000/health
```

For a Hugging Face Spaces-style port:

```powershell
docker run --rm -p 7860:7860 -e PORT=7860 --env-file .env aurelia-api
```

The image builds the **backend only** — `web/` and `frontend/` are excluded via
`.dockerignore`. Hosting steps (HF Spaces / Render / Fly, plus Vercel for the
frontend) are in [`DEPLOY.md`](DEPLOY.md).

---

## 6. CI (GitHub Actions)

`.github/workflows/ci.yml` runs on push/PR to `main`: a backend `pytest` job and
a frontend `lint + build` job. It does **not** deploy. Two intentional choices:

- **Lint is non-blocking** for now (`continue-on-error: true`). After a clean
  local `npm run lint`, remove that line to make it a hard gate.
- **No npm cache** (there's no `web/package-lock.json` yet). Commit one, then
  switch to `npm ci` + enable `cache: npm` in the workflow.

---

## 7. Optional — enable Sentry error monitoring

**Backend:** uncomment `sentry-sdk>=2.0.0` in `requirements.txt` (`pip install`
it), then set `SENTRY_DSN`, `APP_ENV`, `SENTRY_TRACES_SAMPLE_RATE`. A blank DSN is
a complete no-op; a missing package just logs a hint. Init is in
`app/main.py::_init_sentry`.

**Frontend:** set `NEXT_PUBLIC_SENTRY_DSN` in `web/.env.local`. This uses the
built-in dependency-free reporter (`web/lib/observability.ts` + `<ErrorMonitor />`
in `web/app/providers.tsx`) — no npm package needed. To switch to the official
`@sentry/nextjs` instead, see [`DEPLOY.md`](DEPLOY.md) §5.

---

## Files added / changed in this round (Phases 11–13)

**Phase 11–12 (backend, earlier):** `app/cache.py` (Redis/Postgres backends +
fail-open factory), `app/library_repository.py` (status helpers),
`app/main.py` (terminal-status-on-save), `app/routers/library.py`
(`GET /library/{id}/status`), `requirements.txt`; tests
`tests/test_cache_backends.py`, `tests/test_library_status.py`.

**Phase 13 (this round):**

- `Dockerfile`, `.dockerignore` — backend container image.
- `web/vercel.json` — Vercel config + security headers for the `web/` app.
- `web/.eslintrc.json` — ESLint config so `next lint` runs (was missing).
- `.github/workflows/ci.yml` — backend pytest + frontend lint/build.
- `app/config.py` — added `sentry_traces_sample_rate`.
- `app/main.py` — `import logging` + `_init_sentry()` (gated, lazy, fail-safe).
- `requirements.txt` — optional `sentry-sdk` (commented).
- `web/lib/observability.ts` + `web/components/observability/error-monitor.tsx`
  — dependency-free client error reporter; wired into `web/app/providers.tsx`.
- `.env.example` + `web/.env.example` — new Sentry env vars.
- `DEPLOY.md` — full deployment runbook.

---

## What I verified statically (no execution)

- **Sentry init is inert by default:** gated on a non-empty `SENTRY_DSN`, lazily
  imports `sentry_sdk`, and swallows all errors — so importing `app.main` in the
  test suite (no DSN) is a no-op and adds no hard dependency.
- **Frontend reporter never affects the build:** it's plain TS with no
  `@sentry/nextjs` import, a no-op without `NEXT_PUBLIC_SENTRY_DSN`, and guards
  `typeof window` for SSR.
- **Cache/library changes are backward-compatible** (see the prior review): the
  base `Cache` is unchanged and the factory fails open to SQLite.
- **CI mirrors local invocation:** `pytest` from the repo root (matching your
  local runs), and `web/` now has the ESLint config `next lint` requires.
- **`vercel.json` / `.eslintrc.json` are valid JSON; `ci.yml` is valid YAML** by
  inspection.

These are static checks. **Please run §1–§5 yourself to confirm on your machine.**
