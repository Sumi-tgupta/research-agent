-- ============================================================================
-- Aurelia — Supabase schema (Phase 11: normalized, backend-driven library)
-- ----------------------------------------------------------------------------
-- Run this once in your Supabase project's SQL Editor (SQL → New query → paste
-- → Run). It creates the normalized saved-library tables and locks them down
-- with Row Level Security.
--
-- WHO WRITES THESE TABLES
--   The FastAPI backend is the source of truth. It connects over the Postgres
--   connection string (DATABASE_URL, postgresql+pg8000://…) as the database
--   owner role, which BYPASSES RLS, and enforces per-user scoping itself in
--   app/library_repository.py (every query filters on the JWT's user id).
--
--   The RLS policies below are therefore DEFENSE-IN-DEPTH: they matter only if
--   a table is ever reached through Supabase's PostgREST API / anon key (e.g.
--   a future client-direct feature). They do not impede the backend.
--
-- IDENTITY
--   `user_id` is the Supabase auth user id. It is stored as text (varchar(36))
--   — not a FK to auth.users — so the exact same SQLAlchemy models run on
--   SQLite locally and Postgres in production. auth.users.id is a uuid, so the
--   policies compare `auth.uid()::text = user_id`.
--
-- COEXISTENCE WITH ALEMBIC / create_all
--   The backend can also create these tables itself (Base.metadata.create_all
--   on startup for SQLite, or `alembic upgrade head` for Postgres). Table
--   shapes and defaults here mirror app/db/models.py exactly, so whichever
--   path creates them, the ORM reads and writes them identically.
--
-- Supabase is OPTIONAL: the app runs fully anonymously without any of this.
-- You only need it for sign-in + a persistent, per-user saved library.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Clean slate
--   Replaces the Phase 10 client-direct `reports` table (a single table with a
--   `result jsonb` blob), which is a DIFFERENT shape from the normalized
--   `reports` table below and cannot coexist with it under the same name.
--
--   ⚠  THIS DELETES ANY EXISTING SAVED REPORTS. This project is pre-deployment,
--      so that's expected on first setup. If you have data to preserve, comment
--      out this block and migrate manually instead.
-- ----------------------------------------------------------------------------
drop table if exists public.session_tags      cascade;
drop table if exists public.follow_ups        cascade;
drop table if exists public.charts            cascade;
drop table if exists public.claims            cascade;
drop table if exists public.sources           cascade;
drop table if exists public.reports           cascade;
drop table if exists public.research_sessions cascade;
drop table if exists public.tags              cascade;
drop table if exists public.folders           cascade;


-- ----------------------------------------------------------------------------
-- Tables (parents first, for the foreign keys)
-- ----------------------------------------------------------------------------

-- Library folders (optional grouping for saved reports).
create table public.folders (
  id          varchar(36) primary key default gen_random_uuid()::text,
  user_id     varchar(36) not null,
  name        varchar(120) not null,
  created_at  timestamptz not null default now(),
  constraint uq_folder_user_name unique (user_id, name)
);
create index if not exists ix_folders_user_id on public.folders (user_id);

-- Freeform tags.
create table public.tags (
  id          varchar(36) primary key default gen_random_uuid()::text,
  user_id     varchar(36) not null,
  name        varchar(80) not null,
  created_at  timestamptz not null default now(),
  constraint uq_tag_user_name unique (user_id, name)
);
create index if not exists ix_tags_user_id on public.tags (user_id);

-- One saved research run.
create table public.research_sessions (
  id                          varchar(36) primary key default gen_random_uuid()::text,
  user_id                     varchar(36) not null,
  query                       text not null,
  title                       text not null,
  status                      varchar(20) not null default 'complete',
  error_text                  text,
  citation_style              varchar(10) not null default 'apa',
  target_language             varchar(60) not null default 'English',
  num_sub_questions           integer not null default 0,
  max_results_per_subquestion integer not null default 5,
  revision_count              integer not null default 0,
  review_decision             varchar(20) not null default '',
  review_feedback             text not null default '',
  plan_json                   jsonb,
  errors_json                 jsonb,
  folder_id                   varchar(36) references public.folders (id) on delete set null,
  starred                     boolean not null default false,
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now(),
  completed_at                timestamptz
);
create index if not exists ix_research_sessions_user_id   on public.research_sessions (user_id);
create index if not exists ix_research_sessions_status    on public.research_sessions (status);
create index if not exists ix_research_sessions_folder_id on public.research_sessions (folder_id);
create index if not exists ix_session_user_created        on public.research_sessions (user_id, created_at);

-- The written output (1:1 with a session).
create table public.reports (
  id            varchar(36) primary key default gen_random_uuid()::text,
  session_id    varchar(36) not null unique references public.research_sessions (id) on delete cascade,
  final_report  text not null default '',
  draft         text not null default '',
  pdf_url       text,
  created_at    timestamptz not null default now()
);
create index if not exists ix_reports_session_id on public.reports (session_id);

-- Retrieved + ranked documents (mirrors app.schemas.Document).
create table public.sources (
  id               varchar(36) primary key default gen_random_uuid()::text,
  session_id       varchar(36) not null references public.research_sessions (id) on delete cascade,
  ordinal          integer not null default 0,
  title            text not null,
  url              text not null default '',
  authors          jsonb,
  abstract         text,
  snippet          text,
  source           varchar(30) not null,
  kind             varchar(10) not null default 'web',
  published_date   varchar(60),
  citation_count   integer,
  relevance_score  double precision,
  raw_id           varchar(120),
  sub_question     text
);
create index if not exists ix_sources_session_id on public.sources (session_id);

-- Verified claims. supporting/contradicting hold full Document dicts so the
-- frontend's [n] citation numbering reproduces exactly on reopen.
create table public.claims (
  id                     varchar(36) primary key default gen_random_uuid()::text,
  session_id             varchar(36) not null references public.research_sessions (id) on delete cascade,
  ordinal                integer not null default 0,
  text                   text not null,
  sub_question           text not null default '',
  verdict                varchar(20) not null,
  confidence             double precision not null default 0,
  note                   text,
  supporting_sources     jsonb,
  contradicting_sources  jsonb
);
create index if not exists ix_claims_session_id on public.claims (session_id);

-- Chartable comparisons (mirrors app.schemas.ChartSpec).
create table public.charts (
  id          varchar(36) primary key default gen_random_uuid()::text,
  session_id  varchar(36) not null references public.research_sessions (id) on delete cascade,
  ordinal     integer not null default 0,
  title       text not null,
  chart_type  varchar(10) not null default 'bar',
  x_label     varchar(200) not null default '',
  y_label     varchar(200) not null default '',
  labels      jsonb,
  values      jsonb,
  png_url     text
);
create index if not exists ix_charts_session_id on public.charts (session_id);

-- Suggested follow-up questions.
create table public.follow_ups (
  id          varchar(36) primary key default gen_random_uuid()::text,
  session_id  varchar(36) not null references public.research_sessions (id) on delete cascade,
  ordinal     integer not null default 0,
  question    text not null
);
create index if not exists ix_follow_ups_session_id on public.follow_ups (session_id);

-- Session ↔ tag join.
create table public.session_tags (
  id          varchar(36) primary key default gen_random_uuid()::text,
  session_id  varchar(36) not null references public.research_sessions (id) on delete cascade,
  tag_id      varchar(36) not null references public.tags (id) on delete cascade,
  constraint uq_session_tag unique (session_id, tag_id)
);
create index if not exists ix_session_tags_session_id on public.session_tags (session_id);
create index if not exists ix_session_tags_tag_id     on public.session_tags (tag_id);


-- ----------------------------------------------------------------------------
-- Row Level Security (defense-in-depth; see header)
--   Enabling RLS makes each table default-deny for the anon/authenticated
--   roles. The policies then re-open only the caller's own rows. The backend's
--   owner-role connection bypasses all of this.
-- ----------------------------------------------------------------------------

alter table public.folders           enable row level security;
alter table public.tags              enable row level security;
alter table public.research_sessions enable row level security;
alter table public.reports           enable row level security;
alter table public.sources           enable row level security;
alter table public.claims            enable row level security;
alter table public.charts            enable row level security;
alter table public.follow_ups        enable row level security;
alter table public.session_tags      enable row level security;

-- User-owned tables: scope directly on user_id.
drop policy if exists folders_own on public.folders;
create policy folders_own on public.folders
  for all to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

drop policy if exists tags_own on public.tags;
create policy tags_own on public.tags
  for all to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

drop policy if exists research_sessions_own on public.research_sessions;
create policy research_sessions_own on public.research_sessions
  for all to authenticated
  using (auth.uid()::text = user_id)
  with check (auth.uid()::text = user_id);

-- Child tables: scope through the owning session.
drop policy if exists reports_own on public.reports;
create policy reports_own on public.reports
  for all to authenticated
  using (exists (select 1 from public.research_sessions s
                 where s.id = reports.session_id and s.user_id = auth.uid()::text))
  with check (exists (select 1 from public.research_sessions s
                 where s.id = reports.session_id and s.user_id = auth.uid()::text));

drop policy if exists sources_own on public.sources;
create policy sources_own on public.sources
  for all to authenticated
  using (exists (select 1 from public.research_sessions s
                 where s.id = sources.session_id and s.user_id = auth.uid()::text))
  with check (exists (select 1 from public.research_sessions s
                 where s.id = sources.session_id and s.user_id = auth.uid()::text));

drop policy if exists claims_own on public.claims;
create policy claims_own on public.claims
  for all to authenticated
  using (exists (select 1 from public.research_sessions s
                 where s.id = claims.session_id and s.user_id = auth.uid()::text))
  with check (exists (select 1 from public.research_sessions s
                 where s.id = claims.session_id and s.user_id = auth.uid()::text));

drop policy if exists charts_own on public.charts;
create policy charts_own on public.charts
  for all to authenticated
  using (exists (select 1 from public.research_sessions s
                 where s.id = charts.session_id and s.user_id = auth.uid()::text))
  with check (exists (select 1 from public.research_sessions s
                 where s.id = charts.session_id and s.user_id = auth.uid()::text));

drop policy if exists follow_ups_own on public.follow_ups;
create policy follow_ups_own on public.follow_ups
  for all to authenticated
  using (exists (select 1 from public.research_sessions s
                 where s.id = follow_ups.session_id and s.user_id = auth.uid()::text))
  with check (exists (select 1 from public.research_sessions s
                 where s.id = follow_ups.session_id and s.user_id = auth.uid()::text));

drop policy if exists session_tags_own on public.session_tags;
create policy session_tags_own on public.session_tags
  for all to authenticated
  using (exists (select 1 from public.research_sessions s
                 where s.id = session_tags.session_id and s.user_id = auth.uid()::text))
  with check (exists (select 1 from public.research_sessions s
                 where s.id = session_tags.session_id and s.user_id = auth.uid()::text));
