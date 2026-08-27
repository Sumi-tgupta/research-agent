import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import type { ResearchResult } from "@/lib/types";

// Mock only the network layer; keep the real ApiError so the hook's error
// branch behaves as in production.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, streamResearch: vi.fn() };
});

import { useResearch } from "@/lib/use-research";
import { streamResearch } from "@/lib/api";

const mockedStream = vi.mocked(streamResearch);

beforeEach(() => {
  mockedStream.mockReset();
});

describe("useResearch", () => {
  it("marks a finished stage done and activates the next one", async () => {
    mockedStream.mockImplementation(async (_req, { onEvent }) => {
      onEvent({
        type: "stage",
        stage: "planner",
        label: "Planner",
        summary: "Planned",
        errors: [],
      });
    });

    const { result } = renderHook(() => useResearch());
    await act(async () => {
      result.current.start({ query: "hello" });
    });

    expect(result.current.query).toBe("hello");
    const planner = result.current.stages.find((s) => s.stage === "planner");
    const search = result.current.stages.find((s) => s.stage === "search_all");
    expect(planner?.status).toBe("done");
    expect(search?.status).toBe("active");
    expect(result.current.activeStage).toBe("search_all");
  });

  it("captures the result and marks every stage done on complete", async () => {
    const finalResult = { query: "q", final_report: "# Report" } as unknown as ResearchResult;
    mockedStream.mockImplementation(async (_req, { onEvent }) => {
      onEvent({ type: "complete", result: finalResult });
    });

    const { result } = renderHook(() => useResearch());
    await act(async () => {
      result.current.start({ query: "q" });
    });

    expect(result.current.phase).toBe("complete");
    expect(result.current.result).toBe(finalResult);
    expect(result.current.stages.every((s) => s.status === "done")).toBe(true);
    expect(result.current.activeStage).toBeNull();
  });

  it("surfaces a friendly error and enters the error phase when the stream throws", async () => {
    mockedStream.mockRejectedValue(new Error("kaboom"));

    const { result } = renderHook(() => useResearch());
    await act(async () => {
      result.current.start({ query: "q" });
    });

    expect(result.current.phase).toBe("error");
    expect(result.current.error).toBe("kaboom");
  });

  it("resets back to the idle baseline", async () => {
    mockedStream.mockImplementation(async (_req, { onEvent }) => {
      onEvent({
        type: "stage",
        stage: "planner",
        label: "Planner",
        summary: "",
        errors: [],
      });
    });

    const { result } = renderHook(() => useResearch());
    await act(async () => {
      result.current.start({ query: "hello" });
    });
    act(() => {
      result.current.reset();
    });

    expect(result.current.phase).toBe("idle");
    expect(result.current.query).toBe("");
    expect(result.current.result).toBeNull();
    expect(result.current.activeStage).toBeNull();
    expect(result.current.stages.every((s) => s.status === "pending")).toBe(true);
  });
});
