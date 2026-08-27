import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getHorizonState,
  subscribeHorizon,
  setHorizonActivity,
  pulseHorizon,
  resetHorizon,
} from "@/lib/horizon-store";

// The store is a module-level singleton, so reset it before each test.
beforeEach(() => {
  resetHorizon();
});

describe("setHorizonActivity", () => {
  it("clamps the activity target to 0..1", () => {
    setHorizonActivity(0.5);
    expect(getHorizonState().activity).toBe(0.5);
    setHorizonActivity(2);
    expect(getHorizonState().activity).toBe(1);
    setHorizonActivity(-1);
    expect(getHorizonState().activity).toBe(0);
  });
});

describe("pulseHorizon", () => {
  it("accumulates strength and caps at 3", () => {
    pulseHorizon(); // default 1
    expect(getHorizonState().pulse).toBe(1);
    pulseHorizon(5);
    expect(getHorizonState().pulse).toBe(3);
  });
});

describe("resetHorizon", () => {
  it("restores the idle baseline", () => {
    setHorizonActivity(0.9);
    pulseHorizon(2);
    resetHorizon();
    expect(getHorizonState()).toEqual({ activity: 0.12, pulse: 0 });
  });
});

describe("subscribeHorizon", () => {
  it("emits immediately and on every change until unsubscribed", () => {
    const cb = vi.fn();
    const unsubscribe = subscribeHorizon(cb);
    expect(cb).toHaveBeenCalledTimes(1); // immediate replay

    setHorizonActivity(0.4);
    expect(cb).toHaveBeenCalledTimes(2);

    unsubscribe();
    setHorizonActivity(0.6);
    expect(cb).toHaveBeenCalledTimes(2); // no further calls after unsubscribe
  });
});
