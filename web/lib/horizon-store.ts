/**
 * A tiny framework-agnostic store the Emerald Horizon background subscribes to,
 * so the rest of the app can make the field react to what's happening without
 * the WebGL layer importing any React/page code.
 *
 * - `activity` (0..1): ambient intensity target. Idle ~0.12; rises while the
 *   research pipeline runs so the field "wakes up" and its structure tightens.
 * - `pulse`: a transient kick (decays on its own) fired when a pipeline stage
 *   completes — a ripple travels across the horizon.
 *
 * The scene eases toward these values every frame; setters here just record
 * intent. Safe to call during SSR (no window access).
 */

export interface HorizonState {
  activity: number;
  pulse: number;
}

const state: HorizonState = { activity: 0.12, pulse: 0 };
const listeners = new Set<(s: HorizonState) => void>();

function emit() {
  for (const cb of listeners) cb(state);
}

export function getHorizonState(): HorizonState {
  return state;
}

export function subscribeHorizon(cb: (s: HorizonState) => void): () => void {
  listeners.add(cb);
  cb(state);
  return () => {
    listeners.delete(cb);
  };
}

/** Set the ambient intensity target (clamped 0..1). */
export function setHorizonActivity(value: number): void {
  state.activity = Math.min(1, Math.max(0, value));
  emit();
}

/** Fire a transient ripple; strength accumulates and then decays in-scene. */
export function pulseHorizon(strength = 1): void {
  state.pulse = Math.min(3, state.pulse + strength);
  emit();
}

/** Reset to the idle baseline (e.g. when a research run ends). */
export function resetHorizon(): void {
  state.activity = 0.12;
  state.pulse = 0;
  emit();
}
