import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const restBase = env.VITE_REST_URL ?? "http://localhost:8000";
  const wsBase = env.VITE_WS_URL ?? "ws://localhost:8001";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      host: true,
      proxy: {
        "/api": { target: restBase, changeOrigin: true },
        "/ws": { target: wsBase, ws: true, changeOrigin: true },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: mode !== "production",
      target: "es2022",
    },
  };
});
