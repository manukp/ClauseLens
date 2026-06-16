import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output (dist/) is served by the FastAPI process (D7). During dev,
// proxy /api to the backend so the SPA can talk to it without CORS config.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
