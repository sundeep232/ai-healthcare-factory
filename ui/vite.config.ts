import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `npm run dev` proxies /api to the factory API (uvicorn on 127.0.0.1:8000), so the browser
// only ever talks to one origin and no CORS configuration is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
