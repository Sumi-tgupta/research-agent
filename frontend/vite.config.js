import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxies /api/* to the FastAPI backend during `npm run dev`, so the
// frontend can just call fetch("/api/research/stream") without hardcoding
// http://localhost:8000 everywhere or fighting CORS in dev. In production
// you'd put a real reverse proxy (or VITE_API_BASE) in front of this instead.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
