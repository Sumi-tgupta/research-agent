/**
 * Client for the FastAPI research backend.
 *
 * The pipeline streams progress over Server-Sent Events, but the backend
 * exposes it on a POST endpoint (the request carries the query + options),
 * and the native EventSource API is GET-only. So we stream manually with
 * fetch + ReadableStream and parse the `data: {...}\n\n` frames ourselves.
 */

import type {
  ResearchRequest,
  ResearchResult,
  ResearchStreamEvent,
  ChartSpec,
} from "./types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface StreamCallbacks {
  onEvent: (event: ResearchStreamEvent) => void;
  signal?: AbortSignal;
}

/**
 * POST /research/stream and dispatch each parsed SSE event to `onEvent`.
 * Resolves when the stream closes; rejects on network/HTTP failure or abort.
 */
export async function streamResearch(
  request: ResearchRequest,
  { onEvent, signal }: StreamCallbacks
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/research/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new ApiError(
      `Research request failed (${res.status} ${res.statusText}).`,
      res.status
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line.
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const rawFrame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const event = parseSseFrame(rawFrame);
        if (event) onEvent(event);
      }
    }

    // Flush any trailing frame without a terminating blank line.
    const tail = parseSseFrame(buffer);
    if (tail) onEvent(tail);
  } finally {
    reader.releaseLock();
  }
}

/** Extract and JSON-parse the `data:` payload from one SSE frame. */
function parseSseFrame(frame: string): ResearchStreamEvent | null {
  const dataLines = frame
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());

  if (dataLines.length === 0) return null;
  const payload = dataLines.join("\n").trim();
  if (!payload) return null;

  try {
    return JSON.parse(payload) as ResearchStreamEvent;
  } catch {
    return null; // ignore keep-alives / malformed frames
  }
}

/**
 * POST /reports/pdf with an already-computed report and trigger a browser
 * download. Does NOT re-run the pipeline (that's /research/pdf).
 */
export async function downloadReportPdf(params: {
  title: string;
  final_report: string;
  chart_specs?: ChartSpec[];
}): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/reports/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: params.title,
      final_report: params.final_report,
      chart_specs: params.chart_specs ?? [],
    }),
  });

  if (!res.ok) {
    throw new ApiError(
      `Could not generate PDF (${res.status} ${res.statusText}).`,
      res.status
    );
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${slugify(params.title) || "research-report"}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Blocking full-result call — used as a fallback if streaming is unavailable. */
export async function runResearch(
  request: ResearchRequest,
  signal?: AbortSignal
): Promise<ResearchResult> {
  const res = await fetch(`${API_BASE_URL}/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
  if (!res.ok) {
    throw new ApiError(
      `Research request failed (${res.status} ${res.statusText}).`,
      res.status
    );
  }
  return (await res.json()) as ResearchResult;
}

/** GET /health — returns true if the backend is reachable and OK. */
export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/health`, { signal });
    if (!res.ok) return false;
    const data = (await res.json()) as { status?: string };
    return data.status === "ok";
  } catch {
    return false;
  }
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}
