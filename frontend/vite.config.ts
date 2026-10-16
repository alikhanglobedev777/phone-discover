import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Only local tooling uses this proxy. No external JavaScript is fetched or executed.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "DEV_");
  const apiProxyTarget = env.DEV_API_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target: apiProxyTarget, changeOrigin: true },
        "/admin": { target: apiProxyTarget, changeOrigin: true },
      },
    },
  };
});
