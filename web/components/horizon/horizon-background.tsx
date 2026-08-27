"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";

/**
 * Fixed, full-viewport Emerald Horizon background.
 *
 * Layers, back to front:
 *  1. a CSS gradient (`.emerald-horizon-fallback`) — always painted, so the
 *     page never flashes empty and users with no WebGL / reduced motion still
 *     get the identity;
 *  2. the Three.js point field, mounted only when WebGL is available;
 *  3. thin top/bottom fades to keep header and content legible over the field.
 *
 * The heavy `three` bundle is imported dynamically inside the effect so it
 * never runs during SSR and is only paid for on the client.
 */
export function HorizonBackground() {
  const mountRef = useRef<HTMLDivElement>(null);
  // Field instance is typed loosely to avoid importing three types at module scope.
  const fieldRef = useRef<{
    setPalette: (p: unknown) => void;
    setReducedMotion: (r: boolean) => void;
    dispose: () => void;
  } | null>(null);
  const { resolvedTheme } = useTheme();
  const themeRef = useRef(resolvedTheme);
  themeRef.current = resolvedTheme;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    if (!supportsWebGL()) return; // fallback gradient stays

    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let disposed = false;

    (async () => {
      const mod = await import("./horizon-field");
      if (disposed || !mountRef.current) return;
      const { default: HorizonField, DARK_PALETTE, LIGHT_PALETTE } = mod;
      const palette =
        themeRef.current === "light" ? LIGHT_PALETTE : DARK_PALETTE;
      const field = new HorizonField(
        mountRef.current,
        palette,
        media.matches
      );
      fieldRef.current = field as unknown as typeof fieldRef.current;
    })();

    const onMotionChange = () =>
      fieldRef.current?.setReducedMotion(media.matches);
    media.addEventListener?.("change", onMotionChange);

    return () => {
      disposed = true;
      media.removeEventListener?.("change", onMotionChange);
      fieldRef.current?.dispose();
      fieldRef.current = null;
    };
  }, []);

  // Swap palette when the theme changes (field is created once).
  useEffect(() => {
    if (!fieldRef.current) return;
    (async () => {
      const { DARK_PALETTE, LIGHT_PALETTE } = await import("./horizon-field");
      fieldRef.current?.setPalette(
        resolvedTheme === "light" ? LIGHT_PALETTE : DARK_PALETTE
      );
    })();
  }, [resolvedTheme]);

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden emerald-horizon-fallback"
    >
      <div ref={mountRef} className="absolute inset-0" />
      {/* Legibility fades, top and bottom. */}
      <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-background/80 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-56 bg-gradient-to-t from-background/90 to-transparent" />
    </div>
  );
}

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext("webgl") || canvas.getContext("experimental-webgl"))
    );
  } catch {
    return false;
  }
}
