import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  ApiError,
  API_BASE_URL,
  streamResearch,
  checkHealth,
} from "@/lib/api";
import type { ResearchStreamEvent } from "@/lib/types";

/** Build a fetch Response whose body streams the given text chunks as SSE. */
function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return { ok: true, status: 200, statusText: "OK", body } as unknown as Response;
}

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

describe("ApiError", () => {
  it("carries a status and is a real Error", () => {
    const err = new ApiError("boom", 500);
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("ApiError");
    expect(err.message).toBe("boom");
    expect(err.status).toBe(500);
    expect(new ApiError("x").status).toBeUndefined();
  });
});

describe("API_BASE_URL", () => {
  it("never carries a trailing slash", () => {
    expect(API_BASE_URL.endsWith("/")).toBe(false);
  });
});

describe("streamResearch", () => {
  it("parses SSE frames across chunk boundaries, ignores comments, and flushes the tail", async () => {
    const chunks = [
      'data: {"type":"stage","stage":"planner","label":"Planner","summary":"Planned","errors":[]}\n\n' +
        ": heartbeat\n\n" +
        'data: {"type":"stage","stage":"sea',
      'rch_all","label":"Web Search","summary":"Searched","errors":[]}\n\n' +
        'data: {"type":"complete","result":{"query":"q"}}',
    ];
    globalThis.fetch = vi.fn().mockResolvedValue(sseResponse(chunks));

    const events: ResearchStreamEvent[] = [];
    await streamResearch(
      { query: "q" },
      { onEvent: (e) => events.push(e) }
    );

    expect(events).toHaveLength(3);
    expect(events[0]).toMatchObject({ type: "stage", stage: "planner" });
    expect(events[1]).toMatchObject({ type: "stage", stage: "search_all" });
    expect(events[2].type).toBe("complete");
  });

  it("rejects with an ApiError carrying the HTTP status on a failed response", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      body: null,
    } as unknown as Response);

    await expect(
      streamResearch({ query: "q" }, { onEvent: () => {} })
    ).rejects.toMatchObject({ name: "ApiError", status: 503 });
  });
});

describe("checkHealth", () => {
  it("returns true only when the backend reports status ok", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ status: "ok" }) } as unknown as Response);
    expect(await checkHealth()).toBe(true);
  });

  it("returns false when status is not ok", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ status: "degraded" }) } as unknown as Response);
    expect(await checkHealth()).toBe(false);
  });

  it("returns false on a non-2xx response", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue({ ok: false, json: async () => ({}) } as unknown as Response);
    expect(await checkHealth()).toBe(false);
  });

  it("returns false when the request throws", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("network down"));
    expect(await checkHealth()).toBe(false);
  });
});
