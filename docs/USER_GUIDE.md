# User Guide — Aurelia Deep Research Studio

This guide is for using the app once it's running. If you still need to get it
running, start with [`SETUP_AND_RUN.md`](../SETUP_AND_RUN.md).

Aurelia turns a research question into a cited, traceable report. Unlike a chat
answer, everything it tells you is tied back to a real source you can open, and
you can watch the work happen stage by stage instead of waiting for a wall of
text to appear.

---

## Asking a question

The home screen is a single ask box. Type a real research question — the more it
invites evidence from multiple sources, the better the pipeline performs.
Questions that work well tend to be *comparative* or *evidentiary*:

- "How do small modular reactors compare to conventional nuclear?"
- "What is the latest evidence on microplastics in human blood?"
- "Compare GLP-1 drugs for weight loss: efficacy and side effects."

Press **Start research** (or hit Enter). You can also click one of the example
chips to launch a canned question, which is the fastest way to see a full run.

Under the hood the question is broken into several sub-questions, so a single
broad ask fans out into focused searches rather than one shallow lookup.

---

## Watching the run

As soon as you start, the ask box docks to the top and a **live agent tracker**
appears. Each stage lights up as it completes, with a one-line summary of what
it produced:

| Stage | What it means |
|---|---|
| Planner | Broke your question into sub-questions. |
| Web Search | Pulled results from the open web. |
| Paper Retrieval | Pulled academic papers (arXiv, Semantic Scholar, OpenAlex, PubMed, Crossref). |
| Deduplication & Ranking | Collapsed duplicates and ordered sources by relevance. |
| Fact Checking | Cross-referenced claims against sources; flagged contradictions. |
| Writer | Drafted the report from verified claims. |
| Reviewer | Critiqued the draft; may send it back to the Writer to revise. |
| Citation Generator | Compiled the bibliography. |
| Chart Generator | Extracted any chartable numbers. |

If the Reviewer sends the draft back, you'll see **Writer** and **Reviewer** run
a second time — that revision loop is normal and means the report is being
improved, not that something went wrong.

The background responds to the run: it's calm when idle, energizes while agents
are working, and settles once the report is ready. (If you have "reduce motion"
enabled in your OS, the animation is disabled automatically and you get a static
backdrop instead.)

---

## Reading the report

The finished report renders in the main column with proper headings, lists, and
tables. The important part is the citations.

**Inline `[n]` markers** are clickable. Hover one to preview the source in a
card; click it to jump to that source and highlight it. Every claim the report
makes is anchored to a numbered source this way, so you can always check where a
statement came from.

Above or beside the report you'll find tabs for the rest of the result:

- **Report** — the written answer (the default view).
- **Sources** — every source, split into **Web** and **Papers**. Web cards show
  the site, title, and snippet; paper cards show authors, year, venue, and
  abstract. The numbers here match the `[n]` markers in the report.
- **Claims** — the fact-checked claims. Each carries a **verdict** and a
  **confidence** level. When sources disagree, a claim is badged as a
  contradiction (e.g. "⚠ Sources disagree"); expand it to see the conflicting
  sources side by side. This is deliberate — the system surfaces genuine
  disagreement instead of quietly picking a side.
- **Charts** — interactive charts for any numeric data the pipeline could
  extract. If a question has no chartable data, this tab simply says so rather
  than inventing a chart.

---

## Acting on a result

The actions row lets you take the report with you:

- **Copy** the report as Markdown.
- **Download PDF** — a formatted PDF with the report, resolved citations, and
  any charts embedded.
- **Save to library** — keeps the run in your account (requires sign-in; see
  below).

At the bottom, **follow-up suggestion chips** propose related questions. Clicking
one starts a fresh run, so you can pull a thread without retyping.

---

## The command palette

Press **⌘K** (macOS) or **Ctrl+K** (Windows/Linux) anywhere to open the command
palette. From there you can start new research, jump to an example question,
navigate to your library, switch to the report/sources/claims/charts tab,
download the PDF, copy the report, or toggle the theme — all from the keyboard.

---

## Sign-in and your library (optional)

If the deployment has Supabase configured, you'll see a **Sign in** control in
the header (email magic-link or Google). Signing in unlocks:

- **Auto-save**: completed runs are saved to your library automatically.
- **The `/library` page**: browse, search, star, rename, and delete past runs.
  Reopening a saved run reproduces the full report, sources, charts, and working
  citations exactly as they were — and you can re-export the PDF.

Your library is private to you. If sign-in isn't configured on the deployment
you're using, the app runs anonymously and the library page will say so — every
other feature still works.

---

## Themes and accessibility

A **theme toggle** in the header switches between light, dark, and system.
Dark ("Emerald Horizon") is the signature look; light ("misted dawn") tones the
identity down for readability.

The app is built to be used from the keyboard: there's a skip-to-content link
(press Tab from the top of the page), visible focus rings, labels on icon-only
controls, and full respect for your OS "reduce motion" setting.

---

## When something goes wrong

The pipeline is designed to degrade gracefully rather than fail:

- **A source is down or rate-limited.** That source is skipped and the run
  continues with whatever else it found; the miss is noted rather than fatal.
- **You hit a daily quota** (on deployments that enable limits). You'll get a
  clear message telling you when it resets, not a cryptic error.
- **Something breaks mid-run.** You still get a report from whatever the
  pipeline had gathered, instead of the screen hanging on "running" forever.

If the header shows the **backend as offline**, the API isn't reachable — start
it (or wait for a cold-started free host to wake up) and the app reconnects on
its own.
