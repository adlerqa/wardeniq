import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// wardenIQ frontend Vite config.
//
// During `npm run dev`, Vite serves the React app on http://localhost:5173 and
// proxies all /api and /static traffic to the FastAPI backend on :8000. That
// lets us keep the existing FastAPI routes untouched (cookie auth, /api/*
// endpoints, static file serving) while the SPA is developed in isolation.
//
// For production, `npm run build` emits static assets into ../app/static-react
// so FastAPI can serve them alongside (or in place of) the legacy index.html.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/api": {
        target: "http://localhost:8001",
        changeOrigin: true,
        // Cookies must be preserved for the session flow.
        cookieDomainRewrite: "localhost",
      },
    },
  },
  build: {
    outDir: "../app/static-react",
    emptyOutDir: true,
    sourcemap: true,
  },
});
