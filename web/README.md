# Aurelia — Deep Research Studio (web)

The Next.js frontend for the multi-agent research system. It gives the FastAPI
pipeline a live, traceable interface: you ask a question, watch the nine
pipeline stages run in real time, and read a report whose every `[n]` citation
links straight to the source it came from.

The app is **anonymous-first** — it works with nothing configured but the
backend URL. Sign-in and a saved library are optional and light up only when
Supabase credentials are present.

## Stack

Next.js 14 (App Router) · TypeScript · Tailwind CSS with hand-authored
shadcn/ui primitives · Three.js (the reactive "Emerald Horizon" background) ·
Recharts · react-markdown · cmdk · Supabase (optional). No paid services — every
dependency and tier used here is free.

## Prerequisites

Node.js 18.18+ (or 20+) and the backend running. From the repo root:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload    # serves http://localhost:8000
```

## Setup

```bash
cd web
npm install
cp .env.example .env.local        # then edit if needed
npm run dev                        # http://localhost:3000
```

With no `.env.local` at all the app assumes the backend is at
`http://localhost:8000` and runs anonymously.

## Environment

All frontend env vars are optional. See `.env.example` for the annotated list.

`NEXT_PUBLIC_API_BASE_URL` points at the backend (default
`http://localhost:8000`). `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` together enable sign-in and the saved library;
leave them blank to stay anonymous.

## Optional: sign-in + saved library

To turn on accounts and the `/library` page:

1. Create a free project at supabase.com.
2. In the SQL Editor, run `../supabase/schema.sql` (creates the `reports`
   table and its Row Level Security policies).
3. Put the project URL and anon key into `web/.env.local` (the two
   `NEXT_PUBLIC_SUPABASE_*` vars).
4. Optional, for the backend to *recognize* signed-in callers: set
   `SUPABASE_JWT_SECRET` in the repo-root `.env` (Project Settings → API → JWT
   Secret). The backend still never *requires* auth — anonymous requests keep
   working — it just reads the user from the bearer token when one is sent.

Row Level Security means every user only ever sees their own saved reports; the
frontend never filters by user id, the database enforces it.

## How it fits together

`lib/api.ts` streams `POST /research/stream` over `fetch` (Server-Sent Events
framed as `data: {...}`), and `lib/citations.ts` mirrors the backend's source
indexing so `[n]` markers resolve to the exact source. `lib/use-research.ts`
turns the event stream into the live stage tracker and final report.

## Scripts

```bash
npm run dev      # dev server
npm run build    # production build
npm run start    # serve the production build
npm run lint     # eslint
```
