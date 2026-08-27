"use client";

import { useSyncExternalStore, useCallback } from "react";

/**
 * Global open-state store for the auth dialog, so the header button and the
 * command menu can both summon sign-in without prop-drilling. Mirrors
 * use-command-menu.
 */

let open = false;
const listeners = new Set<() => void>();

function emit() {
  for (const cb of listeners) cb();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function getSnapshot() {
  return open;
}

export function setAuthDialogOpen(value: boolean) {
  if (open !== value) {
    open = value;
    emit();
  }
}

export function openAuthDialog() {
  setAuthDialogOpen(true);
}

export function useAuthDialog(): [boolean, (v: boolean) => void] {
  const value = useSyncExternalStore(subscribe, getSnapshot, () => false);
  const set = useCallback((v: boolean) => setAuthDialogOpen(v), []);
  return [value, set];
}
