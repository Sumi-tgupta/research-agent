"""
Load-sanity check for the /research/stream endpoint.

This is a *sanity* probe, not a benchmark: it fires a handful of concurrent
research runs at a locally running backend and reports how the server behaves
under light parallel load — time-to-first-event, total duration, how many
stage events arrived, and (importantly for the free tiers this project targets)
how many requests were shed with HTTP 429 instead of crashing.

Why small numbers by default: a single run drives real Planner/Writer/Reviewer
LLM calls (Gemini/Groq free tier) plus live retrieval (Tavily/Semantic Scholar/
arXiv/…), all of which are rate-limited. Hammering with high concurrency will
mostly measure *their* quotas, not this app. So the defaults stay gentle and
the script frames a 429 as correct, graceful degradation — the rate limiter
(app/rate_limit.py) doing its job — not an error.

Uses only `requests` (already in requirements.txt) + the standard library, so
there's nothing extra to install.

Run it yourself from the project root, with the backend already up
(`uvicorn app.main:app`) in another terminal:

    python -m scripts.load_sanity
    python -m scripts.load_sanity -n 5 --query "impact of microplastics on marine food webs"
    python -m scripts.load_sanity --url http://localhost:8000 -n 3 --num-sub-questions 2 --max-results 3 --stagger 0.5

Flags:
    -n / --concurrency        how many requests to fire at once   (default 3)
    --query                   the research question to send        (default canned)
    --num-sub-questions       planner breadth, 1..10               (default 2, kept low)
    --max-results             results per sub-question, 1..20      (default 3, kept low)
    --url                     backend base URL                     (default http://localhost:8000)
    --timeout                 per-request seconds before giving up (default 300)
    --stagger                 seconds between launches, eases the
                              thundering-herd on free APIs         (default 0.0)

Exit code is 0 when every request either completed or was cleanly rate-limited
(429); it's 1 only if a request failed in an unexpected way (connection error,
timeout, 5xx, or a malformed stream) — handy if you ever wire this into CI.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import requests

DEFAULT_QUERY = "How do small modular reactors compare to conventional nuclear?"


@dataclass
class RunOutcome:
    """What happened to one /research/stream request."""

    index: int
    status: int | None = None          # HTTP status, or None if we never connected
    ttfe: float | None = None          # seconds to the first SSE 'data:' line
    total: float | None = None         # seconds until the stream closed
    stage_events: int = 0              # number of 'stage' events seen
    completed: bool = False            # a 'complete' event arrived
    rate_limited: bool = False         # 429 — graceful degradation, not a failure
    stream_errors: list[str] = field(default_factory=list)  # 'error' events + pipeline errors
    failure: str | None = None         # unexpected failure (transport / 5xx / bad stream)

    @property
    def ok(self) -> bool:
        """A request is 'acceptable' if it finished the pipeline or was shed
        with a 429. Anything else (transport error, 5xx, truncated stream) is
        an unexpected failure the caller should look at."""
        return self.completed or self.rate_limited


def _payload(args: argparse.Namespace) -> dict:
    return {
        "query": args.query,
        "num_sub_questions": args.num_sub_questions,
        "max_results_per_subquestion": args.max_results,
        # Keep the revision loop short so the probe stays quick and cheap.
        "max_revisions": 1,
        "citation_style": "apa",
    }


def _fire_one(index: int, url: str, payload: dict, timeout: float) -> RunOutcome:
    """Issue one streaming request and fold the SSE frames into a RunOutcome.

    SSE framing (see app/stream_events.format_sse_event): each event is a single
    'data: {json}\\n\\n' frame. requests' iter_lines() hands us the 'data: …'
    line followed by a blank line; we parse the JSON after 'data:' and switch on
    its 'type' (stage | error | complete).
    """
    outcome = RunOutcome(index=index)
    start = time.monotonic()
    try:
        resp = requests.post(
            f"{url.rstrip('/')}/research/stream",
            json=payload,
            stream=True,
            timeout=timeout,
            headers={"Accept": "text/event-stream"},
        )
        outcome.status = resp.status_code

        if resp.status_code == 429:
            # The daily quota (app/rate_limit.py) turned us away. Expected under
            # load on a free deployment — record it and move on, don't retry.
            outcome.rate_limited = True
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                outcome.stream_errors.append(f"rate limited; Retry-After={retry_after}s")
            resp.close()
            outcome.total = time.monotonic() - start
            return outcome

        if resp.status_code != 200:
            body = ""
            try:
                body = resp.text[:200]
            except Exception:
                pass
            outcome.failure = f"HTTP {resp.status_code}: {body}".strip()
            resp.close()
            outcome.total = time.monotonic() - start
            return outcome

        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue  # blank separators and any keep-alive comments
            if outcome.ttfe is None:
                outcome.ttfe = time.monotonic() - start
            try:
                event = json.loads(raw[len("data:"):].strip())
            except json.JSONDecodeError:
                outcome.stream_errors.append("could not parse an SSE frame")
                continue

            etype = event.get("type")
            if etype == "stage":
                outcome.stage_events += 1
                for err in event.get("errors") or []:
                    outcome.stream_errors.append(str(err))
            elif etype == "error":
                outcome.stream_errors.append(str(event.get("message", "unknown error")))
            elif etype == "complete":
                outcome.completed = True
                result = event.get("result") or {}
                for err in result.get("errors") or []:
                    outcome.stream_errors.append(str(err))

        outcome.total = time.monotonic() - start
        if not outcome.completed:
            # Stream ended without the terminal event — the pipeline never
            # signalled done, which is exactly the kind of thing this probe
            # exists to catch.
            outcome.failure = "stream ended without a 'complete' event"
    except requests.exceptions.Timeout:
        outcome.total = time.monotonic() - start
        outcome.failure = f"timed out after {timeout:.0f}s"
    except requests.exceptions.RequestException as exc:
        outcome.total = time.monotonic() - start
        outcome.failure = f"transport error: {exc}"
    return outcome


def _preflight(url: str, timeout: float = 5.0) -> bool:
    """Confirm the backend is actually up before we fan out, so a typo in --url
    doesn't masquerade as N identical connection failures."""
    try:
        resp = requests.get(f"{url.rstrip('/')}/health", timeout=timeout)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


def _fmt(seconds: float | None) -> str:
    return "  —  " if seconds is None else f"{seconds:6.1f}s"


def _percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile — robust for the tiny samples this probe
    produces (statistics.quantiles needs n>=2 and interpolates)."""
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1))))
    return ordered[k]


def _report(outcomes: list[RunOutcome]) -> None:
    print("\nPer-request:")
    print(f"  {'#':>2}  {'status':>6}  {'first-event':>11}  {'total':>7}  {'stages':>6}  result")
    for o in sorted(outcomes, key=lambda x: x.index):
        if o.rate_limited:
            result = "rate-limited (429) — graceful"
        elif o.completed and not o.stream_errors:
            result = "completed"
        elif o.completed:
            result = f"completed with {len(o.stream_errors)} pipeline note(s)"
        else:
            result = f"FAILED — {o.failure or 'unknown'}"
        status = str(o.status) if o.status is not None else "—"
        print(f"  {o.index:>2}  {status:>6}  {_fmt(o.ttfe):>11}  {_fmt(o.total):>7}  {o.stage_events:>6}  {result}")

    completed = [o for o in outcomes if o.completed]
    rate_limited = [o for o in outcomes if o.rate_limited]
    failed = [o for o in outcomes if not o.ok]

    totals = [o.total for o in completed if o.total is not None]
    ttfes = [o.ttfe for o in completed if o.ttfe is not None]

    print("\nSummary:")
    print(f"  requests fired      : {len(outcomes)}")
    print(f"  completed           : {len(completed)}")
    print(f"  rate-limited (429)  : {len(rate_limited)}   (expected on free tiers — graceful degradation)")
    print(f"  unexpected failures : {len(failed)}")
    if totals:
        print(
            "  total   (s)         : "
            f"min {min(totals):.1f} | p50 {_percentile(totals, 50):.1f} | "
            f"p95 {_percentile(totals, 95):.1f} | max {max(totals):.1f}"
        )
    if ttfes:
        print(
            "  first-event (s)     : "
            f"min {min(ttfes):.1f} | p50 {_percentile(ttfes, 50):.1f} | "
            f"p95 {_percentile(ttfes, 95):.1f} | max {max(ttfes):.1f}"
        )

    # Surface a few distinct pipeline notes without drowning the summary.
    notes = {err for o in outcomes for err in o.stream_errors}
    if notes:
        print("\n  Pipeline/stream notes (deduped):")
        for note in list(notes)[:8]:
            print(f"    - {note}")
        if len(notes) > 8:
            print(f"    … and {len(notes) - 8} more")

    if failed:
        print(
            "\nResult: some requests failed unexpectedly (see 'FAILED' rows above). "
            "A 429 is NOT a failure; a connection error, 5xx, timeout, or truncated "
            "stream is."
        )
    else:
        print("\nResult: healthy — every request either completed or was cleanly rate-limited.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Load-sanity probe for /research/stream.")
    parser.add_argument("-n", "--concurrency", type=int, default=3, help="requests to fire at once (default 3)")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="research question to send")
    parser.add_argument("--num-sub-questions", type=int, default=2, help="planner breadth 1..10 (default 2)")
    parser.add_argument("--max-results", type=int, default=3, help="results per sub-question 1..20 (default 3)")
    parser.add_argument("--url", default="http://localhost:8000", help="backend base URL")
    parser.add_argument("--timeout", type=float, default=300.0, help="per-request timeout seconds (default 300)")
    parser.add_argument("--stagger", type=float, default=0.0, help="seconds between launches (default 0)")
    args = parser.parse_args()

    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")

    print(f"Load-sanity: {args.concurrency} concurrent request(s) → {args.url}/research/stream")
    print(f"Query: {args.query!r}  (sub-questions={args.num_sub_questions}, max-results={args.max_results})")
    print("Note: this spends real free-tier quota (LLM + retrieval APIs). Keep concurrency modest.\n")

    if not _preflight(args.url):
        print(
            f"Backend didn't answer /health at {args.url}. Start it first:\n"
            "    uvicorn app.main:app --reload\n"
            "then re-run this probe.",
            file=sys.stderr,
        )
        return 1

    payload = _payload(args)
    outcomes: list[RunOutcome] = []

    wall_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = []
        for i in range(1, args.concurrency + 1):
            futures.append(pool.submit(_fire_one, i, args.url, payload, args.timeout))
            if args.stagger > 0 and i < args.concurrency:
                time.sleep(args.stagger)
        for fut in as_completed(futures):
            outcomes.append(fut.result())
    wall = time.monotonic() - wall_start

    _report(outcomes)
    print(f"\nWall-clock for the whole batch: {wall:.1f}s")

    return 0 if all(o.ok for o in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
