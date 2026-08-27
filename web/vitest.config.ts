/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import path from "node:path";

// `@/...` resolves to the web/ root, mirroring tsconfig `paths`.
const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": rootDir,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Unit/component tests only. Playwright E2E lives in tests/e2e and is run
    // separately (`npm run test:e2e`) — keep it out of the Vitest run.
    include: ["tests/unit/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["tests/e2e/**", "node_modules/**"],
    css: false,
    coverage: {
      provider: "v8",
      reportsDirectory: "./coverage",
      include: ["lib/**/*.ts", "components/**/*.tsx"],
      exclude: ["**/*.d.ts", "tests/**"],
    },
  },
});
