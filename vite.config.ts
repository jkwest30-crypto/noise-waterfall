import { defineConfig } from "vite";

// The Python engine owns every number, so the dev server proxies to it rather
// than the frontend reimplementing anything.
const ENGINE_PORT = 8317;
const ENGINE = `http://localhost:${ENGINE_PORT}`;

export default defineConfig({
  root: "web",
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    // Deliberately off the common 5173: another project on this machine already
    // uses it, and Vite silently falls back to the next free port when the
    // requested one is taken. strictPort turns that into a loud failure, so a
    // test run can never end up pointed at somebody else's app.
    port: 5373,
    strictPort: true,
    proxy: {
      "/ws": { target: `ws://localhost:${ENGINE_PORT}`, ws: true },
      "/render": ENGINE,
      "/health": ENGINE,
    },
  },
});
