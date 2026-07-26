import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/ui",
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:5373" },
  projects: [
    {
      name: "chromium",
      use: {
        browserName: "chromium",
        launchOptions: {
          args: [
            // SwiftShader gives deterministic software WebGL in headless CI.
            "--use-gl=swiftshader",
            "--enable-unsafe-swiftshader",
            // Let OfflineAudioContext and AudioContext run without a gesture.
            "--autoplay-policy=no-user-gesture-required",
          ],
        },
      },
    },
  ],
  // Both halves of the app: the Python engine that computes every number, and
  // the Vite server that renders them.
  webServer: [
    {
      command: ".venv/bin/python -m uvicorn waterfall.api.app:app --port 8317 --reload --reload-dir src",
      url: "http://localhost:8317/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "npm run dev",
      url: "http://localhost:5373",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
