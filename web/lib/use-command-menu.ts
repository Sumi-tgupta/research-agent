"use client";

import { useSyncExternalStore, useCallback } from "react";

/**
 * Tiny global store for the ⌘K command menu's open state, so the header
 * trigger, the keyboard shortcut, and the menu itself stay decoupled (no
 * prop-drilling through the layout).
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

export function setCommandMenuOpen(value: boolean) {
  if (open !== value) {
    open = value;
    emit();
  }
}

export function openCommandMenu() {
  setCommandMenuOpen(true);
}

export function toggleCommandMenu() {
  setCommandMenuOpen(!open);
}

export function useCommandMenu(): [boolean, (v: boolean) => void] {
  const value = useSyncExternalStore(
    subscribe,
    getSnapshot,
    () => false // SSR: closed
  );
  const set = useCallback((v: boolean) => setCommandMenuOpen(v), []);
  return [value, set];
}
