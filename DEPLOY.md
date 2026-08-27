# Deployment runbook

How to take Aurelia from this repo to a live, **entirely free-tier** deployment.
Two independent pieces ship separately:

```
                    ┌─────────────────────────┐
  Browser  ───────▶ │  Frontend (Next.js)     │   Vercel  (free Hobby)
                    │  web/                    │
                    └───────────┬─────────────┘
                                │ HTTPS (NEXT_PUBLIC_API_BASE_URL)
                                ▼
                    ┌─────────────────────────┐
                    │  Backend API (FastAPI)  │   HF Spaces / Render / Fly (free)
                    │  Dockerfile → app.main  │
                    └───────────┬─────────────┘
                                │ DATABASE_URL (postgresql+pg8000://…)
                                ▼
                    ┌─────────────────────────┐
                    │  Postgres + Auth        │   Supabase  (free)
                    │  supabase/schema.sql    │
                    └─────────────────────────┘
```

| Piece            | Lives in          | Deploys to                         | Config source        |
| ---------------- | ----------------- | ---------------------------------- | -------------------- |
| Backend API      | `Dockerfile`, `app/` | HF Spaces **or** Render **or** Fly | `.env` / host env    |
| Frontend         | `web/`            | Vercel                             | `web/.env.local` / Vercel env |
| Database + Auth  | `supabase/schema.sql`, `migrations/` | Supabase        | SQL editor + `DATABASE_URL` |
| CI               | `.github/workflows/ci.yml` | GitHub Actions            | repo push / PR       |

> **Everything below is optional and free.** With none of it configured, the app
> still runs locally and anonymously (SQLite, no sign-in, no monitoring). Add
> each piece only when you want it. See `RUN_PHASES_11_13.md` for the local
> run/test commands.

> **Nothing in this runbook has been executed for you.** These are the commands
> to run yourself, on your own accounts, when you're ready to deploy.

---

## 0. Prerequisites (all have a free tier, no card required)

- A GitHub account with this repo pushed to it.
- [Supabase](https://supabase.com) account — Postgres + auth (optional but needed for sign-in and the saved library).
- One backend host: [Hugging Face](https://huggingface.co) Spaces, [Render](https://render.com), or [Fly.io](https://fly.io).
- [Vercel](https://vercel.com) account — frontend.
- API keys from `.env.example` (Gemini, plus a web-search key — Exa or Serper — and optionally Groq; all free tier).

---

## 1. Database — Supabase Postgres (optional)

Skip this entire section to run the backend on local SQLite (zero setup). Do it
when you want persistence across restarts, sign-in, and the saved library.

1. Create a Supabase project. Choose a strong database password and save it.
2. **Run the RLS schema.** Open **SQL Editor → New query**, paste the contents of
   [`supabase/schema.sql`](supabase/schema.sql), and **Run**. This creates the
   normalized library tables with Row-Level Security (defense-in-depth — the
   backend enforces per-user scoping itself; see the file's header comment).
3. **Get the connection string.** Project Settings → Database → Connection string.
   Rewrite it to use the pure-Python `pg8000` driver this project ships with:

   ```
   postgresql+pg8000://postgres:YOUR_PASSWORD@db.YOUR_REF.supabase.co:5432/postgres
   ```

   This value is your `DATABASE_URL`.
4. **Apply migrations.** From a checkout with the deps installed (see
   `RUN_PHASES_11_13.md`), point Alembic at the production DB and upgrade:

   ```bash
   export DATABASE_URL="postgresql+pg8000://postgres:YOUR_PASSWORD@db.YOUR_REF.supabase.co:5432/postgres"
   alembic upgrade head
   ```

   `migrations/env.py` reads `DATABASE_URL` from the app config, so this targets
   the same database the API uses. Revisions applied: `0001_phase11_library`,
   `0002_phase12_usage_counters`. (Locally on SQLite the tables auto-create on
   startup, so this step is Postgres-only.)
5. **For auth**, grab Project Settings → API → **JWT Secret** (backend
   `SUPABASE_JWT_SECRET`), **Project URL** and **anon public** key (frontend
   `NEXT_PUBLIC_SUPABASE_*`).

---

## 2. Backend API — Docker to a free host

The `Dockerfile` builds the FastAPI service only (the frontend is excluded via
`.dockerignore`). The container binds `$PORT` and exposes `GET /health` for the
platform health check.

**Backend environment variables** (set these on whichever host you pick):

| Variable | Needed? | Notes |
| --- | --- | --- |
| `GEMINI_API_KEY` | Yes | Free at aistudio.google.com |
| `GROQ_API_KEY` | Recommended | Enables fast-model routing + fallback |
| `EXA_API_KEY` | Recommended | Primary web search (free monthly credit) |
| `SERPER_API_KEY` | Recommended | Web-search fallback (~2,500 free lookups); keyless DuckDuckGo backstops both |
| `DATABASE_URL` | For persistence | `postgresql+pg8000://…` from step 1; else SQLite (ephemeral) |
| `CACHE_BACKEND` | Recommended | `postgres` or `redis` in prod (see §4) |
| `ALLOWED_ORIGINS` | Yes for prod | Your Vercel URL(s), comma-separated (see §3) |
| `SUPABASE_JWT_SECRET`, `SUPABASE_URL` | For auth | Recognizes signed-in users |
| `RATE_LIMIT_ENABLED` | Optional | `true` on a public deploy (see §4) |
| `SENTRY_DSN`, `APP_ENV`, `SENTRY_TRACES_SAMPLE_RATE` | Optional | See §5 |

### Option A — Hugging Face Spaces (Docker SDK)

1. Create a new **Space** → SDK: **Docker** → **Blank**. Push this repo to it
   (or connect the GitHub repo).
2. Spaces serve on port **7860**. Declare it in the Space's `README.md` front
   matter and set a matching variable:

   ```yaml
   ---
   title: Aurelia API
   sdk: docker
   app_port: 7860
   ---
   ```

   Then add Space **Variables/Secrets**: `PORT=7860` plus the env vars above.
   (The container's `CMD` honors `$PORT`, so 7860 just works.)
3. The Space builds the Dockerfile and starts the API. Watch the build logs.

### Option B — Render (Docker)

1. **New → Web Service** → connect the repo → Runtime: **Docker**.
2. Render injects `PORT` automatically — no action needed; the container binds it.
3. Set **Health Check Path** to `/health`.
4. Add the env vars above under **Environment**.

### Option C — Fly.io (Docker)

1. `fly launch` in the repo root (it detects the `Dockerfile`; decline to deploy
   immediately so you can set secrets first).
2. In `fly.toml` set `internal_port = 8000` (the image's default bind).
3. `fly secrets set GEMINI_API_KEY=… GROQ_API_KEY=… DATABASE_URL=… ALLOWED_ORIGINS=…`
4. `fly deploy`.

### Verify the backend

```bash
curl https://YOUR-BACKEND-URL/health
# → {"status":"ok","phases_complete":[0,1,2,3,4,5,6]}
```

Note this base URL — the frontend needs it next.

---

## 3. Frontend — Vercel

1. **New Project** → import this GitHub repo.
2. **Set the Root Directory to `web`.** This is the single most important
   setting: the Next.js app lives in the `web/` subdirectory, not the repo root.
   Vercel then auto-detects Next.js — leave build/output commands at their
   defaults. `web/vercel.json` supplies safe security headers.
3. Add **Environment Variables** (Project → Settings → Environment Variables):

   | Variable | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_BASE_URL` | Your backend URL from §2 |
   | `NEXT_PUBLIC_SUPABASE_URL` | Supabase Project URL (only for auth) |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon public key (only for auth) |
   | `NEXT_PUBLIC_SENTRY_DSN` | Optional — see §5 |

   `NEXT_PUBLIC_*` values are inlined **at build time**, so changing one requires
   a redeploy. All have safe defaults, so a build never fails for a missing one.
4. Deploy. Note the resulting URL, e.g. `https://your-app.vercel.app`.
5. **Close the CORS loop:** set the backend's `ALLOWED_ORIGINS` to that Vercel URL
   (comma-separate multiple, e.g. your custom domain) and redeploy the backend.
   Preview deployments use per-branch subdomains; add them explicitly or use
   `*` only for short-lived testing.

---

## 4. Production hardening (optional, still free)

**Cache backend.** Free host filesystems are ephemeral, so the default SQLite
cache file is wiped on redeploy. Keep the retrieval cache warm across restarts:

- `CACHE_BACKEND=postgres` — reuses `DATABASE_URL`; zero extra services.
- `CACHE_BACKEND=redis` + `REDIS_URL=…` — e.g. a free [Upstash](https://upstash.com)
  Redis. Also uncomment `redis>=5.0.0` in `requirements.txt` (it's lazily
  imported; the app fails open to SQLite if it can't connect).

**Rate limiting.** On a shared/public deploy set `RATE_LIMIT_ENABLED=true`
(defaults: 50/day signed-in, 10/day anonymous by IP; counts reset daily UTC).

---

## 5. Error monitoring — Sentry (optional, free tier)

### Backend

The backend init is **env-driven and lazy** (`app/main.py::_init_sentry`): a
blank `SENTRY_DSN` is a complete no-op, and `sentry-sdk` is an optional package.

1. Create a free Sentry project (platform: Python / FastAPI) and copy its DSN.
2. Uncomment `sentry-sdk>=2.0.0` in `requirements.txt` (or `pip install sentry-sdk`).
3. Set env vars on the backend host:

   ```
   SENTRY_DSN=https://…@…ingest.sentry.io/…
   APP_ENV=production
   SENTRY_TRACES_SAMPLE_RATE=0.0     # errors only; raise toward 1.0 for tracing
   ```

   If the DSN is set but the SDK isn't installed, the app logs a hint and keeps
   running — monitoring never blocks startup.

### Frontend

This repo ships a **tiny dependency-free reporter** (`web/lib/observability.ts`,
mounted by `<ErrorMonitor />` in `app/providers.tsx`). It captures unhandled
errors and promise rejections and POSTs a minimal Sentry envelope directly to
the ingest endpoint. It's a no-op unless a DSN is set, and requires **no npm
package**, so it never affects your build.

- Set `NEXT_PUBLIC_SENTRY_DSN` (create a Sentry project of platform
  **Browser/JavaScript**) in Vercel. Optionally `NEXT_PUBLIC_SENTRY_ENVIRONMENT`
  and `NEXT_PUBLIC_SENTRY_RELEASE`.

**Want the full experience instead** (tracing, session replay, source-mapped
stack traces)? Install the official SDK and remove the built-in reporter:

```bash
cd web && npm install @sentry/nextjs && npx @sentry/wizard@latest -i nextjs
```

Then delete `<ErrorMonitor />` from `web/app/providers.tsx` (and optionally
`web/lib/observability.ts` + `web/components/observability/`) so the two don't
double-report.

---

## 6. Continuous integration — GitHub Actions

`.github/workflows/ci.yml` runs on every push/PR to `main`:

- **Backend · pytest** — Python 3.13, installs `requirements.txt`, runs `pytest`.
- **Frontend · lint & build** — Node 20, `npm install`, `npm run lint`, `npm run build`.

Two deliberate choices, both easy to tighten later:

- **Lint is non-blocking** (`continue-on-error: true`). Once you've confirmed a
  clean local `cd web && npm run lint`, remove that line to make lint a hard gate.
- **No npm cache** in the frontend job, because `web/` has no committed lockfile.
  Commit a `web/package-lock.json`, then switch the install step to `npm ci` and
  add `cache: npm` + `cache-dependency-path: web/package-lock.json` to
  `actions/setup-node` for faster, reproducible installs.

CI does not deploy. Vercel deploys on push via its own GitHub integration; the
backend redeploys per your host's settings.

---

## 7. Environment variable reference

**Backend** (`.env` locally; host env in prod) — full list and comments in
[`.env.example`](.env.example):

```
GEMINI_API_KEY=            GROQ_API_KEY=
EXA_API_KEY=               SERPER_API_KEY=         SEARCH_PROVIDER=auto
DATABASE_URL=              CACHE_BACKEND=sqlite    REDIS_URL=
ALLOWED_ORIGINS=           RATE_LIMIT_ENABLED=false
SUPABASE_JWT_SECRET=       SUPABASE_URL=
SENTRY_DSN=                APP_ENV=development     SENTRY_TRACES_SAMPLE_RATE=0.0
```

**Frontend** (`web/.env.local` locally; Vercel env in prod) — see
[`web/.env.example`](web/.env.example):

```
NEXT_PUBLIC_API_BASE_URL=  NEXT_PUBLIC_SUPABASE_URL=   NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_SENTRY_DSN=     NEXT_PUBLIC_SENTRY_ENVIRONMENT=   NEXT_PUBLIC_SENTRY_RELEASE=
```

Secrets (`*_API_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_KEY`, `DATABASE_URL`)
live **only** in backend/host env — never in `NEXT_PUBLIC_*`, never committed.

---

## 8. Post-deploy smoke checklist

1. `curl https://BACKEND/health` returns `{"status":"ok",…}`.
2. Open the Vercel URL; run a research query end to end.
3. Browser devtools **Network** tab shows calls hitting your backend URL with no
   CORS errors (if you see CORS errors, fix `ALLOWED_ORIGINS` in §3).
4. (If auth) Sign in; save a report; confirm it appears in the library after a
   reload (proves `DATABASE_URL` persistence).
5. (If Sentry) Trigger a test error and confirm it lands in your Sentry project.
