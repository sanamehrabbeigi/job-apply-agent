import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `npm run build` writes into the Python package so `job-agent serve` can serve the UI without Node.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/job_apply_agent/web/static", emptyOutDir: true },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  test: { environment: "node" },
});
