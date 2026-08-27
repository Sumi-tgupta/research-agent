/**
 * Optional, dependency-free client error monitoring.
 *
 * Mirrors the Supabase pattern (lib/supabase/config.ts): the whole thing is a
 * no-op unless NEXT_PUBLIC_SENTRY_DSN is set, so the app builds and runs with
 * zero configuration and zero extra npm packages.
 *
 * When a DSN *is* set, this installs global `error` / `unhandledrejection`
 * listeners and posts a minimal Sentry "envelope" straight to the ingest
 * endpoint over fetch(). That deliberately avoids pulling in @sentry/nextjs,
 * which would be a hard build-time dependency. If you outgrow this and want
 * tracing, session replay, or source-mapped stack traces, install
 * @sentry/nextjs instead and drop <ErrorMonitor /> from app/providers.tsx —
 * see DEPLOY.md for that path.
 */

export const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN ?? "";
const ENVIRONMENT =
  process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ??
  process.env.NODE_ENV ??
  "development";
const RELEASE = process.env.NEXT_PUBLIC_SENTRY_RELEASE ?? "";

export function isErrorMonitoringConfigured(): boolean {
  return Boolean(SENTRY_DSN);
}

/** Turn a DSN (https://<key>@<host>/<projectId>) into its envelope endpoint. */
function parseEnvelopeUrl(dsn: string): string | null {
  try {
    const url = new URL(dsn);
    const publicKey = url.username;
    const projectId = url.pathname.replace(/^\//, "");
    if (!publicKey || !projectId) return null;
    return `${url.protocol}//${url.host}/api/${projectId}/envelope/?sentry_key=${publicKey}&sentry_version=7`;
  } catch {
    return null;
  }
}

/** 32-char lowercase hex, no dashes — the id shape Sentry expects. */
function makeEventId(): string {
  const raw =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return raw.replace(/-/g, "").padEnd(32, "0").slice(0, 32);
}

let installed = false;
// Cheap flood guard: don't send the same message more than once per page load.
const seen = new Set<string>();

function report(
  envelopeUrl: string,
  opts: { type: string; value: string; stack?: string; url: string }
): void {
  const key = `${opts.type}:${opts.value}`;
  if (seen.has(key)) return;
  seen.add(key);

  const eventId = makeEventId();
  const header = JSON.stringify({
    event_id: eventId,
    sent_at: new Date().toISOString(),
    dsn: SENTRY_DSN,
  });
  const itemHeader = JSON.stringify({ type: "event" });

  const event: Record<string, unknown> = {
    event_id: eventId,
    timestamp: Date.now() / 1000,
    platform: "javascript",
    level: "error",
    environment: ENVIRONMENT,
    exception: { values: [{ type: opts.type, value: opts.value }] },
    request: { url: opts.url },
  };
  if (RELEASE) event.release = RELEASE;
  if (opts.stack) event.extra = { stack: opts.stack };

  const body = `${header}\n${itemHeader}\n${JSON.stringify(event)}`;

  try {
    // keepalive lets the request survive a page unload; failures are swallowed
    // because error monitoring must never surface errors of its own.
    void fetch(envelopeUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-sentry-envelope" },
      body,
      keepalive: true,
      mode: "cors",
    }).catch(() => {});
  } catch {
    /* ignore */
  }
}

/**
 * Install global error listeners once. Safe to call on every mount; it's a
 * no-op without a DSN, on the server, or after the first successful install.
 */
export function initClientErrorMonitoring(): void {
  if (installed) return;
  if (typeof window === "undefined") return;
  if (!SENTRY_DSN) return;

  const envelopeUrl = parseEnvelopeUrl(SENTRY_DSN);
  // A malformed DSN degrades to a no-op rather than throwing.
  installed = true;
  if (!envelopeUrl) return;

  window.addEventListener("error", (e: ErrorEvent) => {
    const err = e.error as Error | undefined;
    report(envelopeUrl, {
      type: err?.name || "Error",
      value: err?.message || e.message || "Unknown error",
      stack: err?.stack,
      url: window.location.href,
    });
  });

  window.addEventListener("unhandledrejection", (e: PromiseRejectionEvent) => {
    const reason = e.reason;
    const isErr = reason instanceof Error;
    report(envelopeUrl, {
      type: isErr ? reason.name : "UnhandledRejection",
      value: isErr ? reason.message : String(reason),
      stack: isErr ? reason.stack : undefined,
      url: window.location.href,
    });
  });
}
