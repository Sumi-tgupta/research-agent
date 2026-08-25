# Frontend — Research Ledger

A React (Vite) single-page app for the multi-agent research pipeline built
in Phases 1-5. Query in, live agent-by-agent status while the pipeline
runs, final report out, with a PDF download.

## Setup

Requires Node 18+.

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173 — **with the backend already running**
(`uvicorn app.main:app --reload` from the project root, default port
8000). The dev server proxies `/api/*` to `http://localhost:8000` (see
`vite.config.js`), so the frontend never needs to know the backend's URL
directly.

```bash
npm run build      # production build -> dist/
npm run preview    # serve the production build locally
```

## How it talks to the backend

Three endpoints, all built in earlier phases:

- `POST /api/research/stream` — Server-Sent Events, one per pipeline
  stage. The browser's native `EventSource` only does GET requests, and
  the query is a JSON POST body, so `src/api.js` reads the streaming
  response body directly with `fetch()` and parses `data: {...}` frames
  out of it by hand instead.
- `POST /api/reports/pdf` — takes the already-computed report from the
  stream's final event and renders it to a PDF, without re-running the
  (slower, rate-limited) pipeline just to get a download.

## Structure

```
src/
  main.jsx                  entry point
  App.jsx                   state machine: idle -> running -> complete
  api.js                    SSE client + PDF download helper
  index.css                 design tokens + all styles (no CSS framework)
  components/
    QueryForm.jsx             research question + language/citation/depth options
    PipelineStatus.jsx         live agent-by-agent status — see below
    ReportView.jsx              final markdown report + chart preview + download
```

## Design notes

The palette isn't decorative — it's the same three colors the Fact
Checker already uses for a claim's verdict (`--verified` teal,
`--caution` amber, `--alert` rust), reused for both the live pipeline
status stamps and the report's confidence-summary chips. A stage that
completes cleanly gets a teal "Done" stamp; one that had to fall back to
something (no API key, a failed call) gets an amber "Done, with notes"
stamp instead of hiding that it happened.

Typography is the IBM Plex superfamily throughout — Serif for headings,
Sans for body text, Mono for stage labels/status/citations — one type
family with three clearly different jobs, rather than several unrelated
fonts.

**`PipelineStatus.jsx` is the signature element.** Since
`/research/stream` yields a fresh event every time a node runs — including
every pass through the Writer/Reviewer revision loop — the live status
view is a numbered, append-only log (a research ledger, not a progress
bar), where each entry "stamps" itself done when its event arrives. If the
Reviewer sends a draft back for revision, you see "Writer" appear a
second time in the log, not just a stuck progress bar — this is the part
of the app that's actually demonstrating multiple agents at work.

## Known limitation

Chart previews in the browser are simple hand-rolled CSS bars, not the
actual matplotlib output — `chart_specs` from `/research/stream` is just
data (title/labels/values); real PNG rendering only happens server-side,
on demand, when a PDF is requested (see `app/chart_render.py`). The
downloaded PDF has the real charts; the in-page preview is an
approximation so you don't have to download a PDF just to see there's a
chart at all.
