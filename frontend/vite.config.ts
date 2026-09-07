import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = "http://localhost:8000";
const frontendRoot = fileURLToPath(new URL(".", import.meta.url));

// The version shown on the login page. Releases stamp the real tag via the
// ORYH_APP_VERSION build arg (see Dockerfile / deploy.sh); otherwise fall back
// to package.json so a bare `npm run build` still shows something meaningful.
const packageVersion = JSON.parse(
  readFileSync(`${frontendRoot}/package.json`, "utf-8"),
).version as string;
const appVersion = process.env.ORYH_APP_VERSION?.trim() || packageVersion;

// Console only. The public website is its own project (../site) with its own
// build and container; nothing here carries marketing code.
export default defineConfig(async ({ mode, command }) => {
  if (mode === "preview" && command !== "serve")
    throw new Error(
      "Sample preview is dev-only; use the default mode for production builds.",
    );
  const preview = mode === "preview";
  const previewPlugin = preview
    ? (await import("./preview/consolePreview")).consolePreview()
    : null;
  return {
    base: "/console/",
    define: {
      __APP_VERSION__: JSON.stringify(appVersion),
    },
    plugins: [react(), ...(previewPlugin ? [previewPlugin] : [])],
    build: {
      outDir: "dist",
    },
    server: {
      host: "127.0.0.1",
      proxy: preview
        ? undefined
        : {
            "/api": apiTarget,
            "/web": apiTarget,
            "/admin": apiTarget,
          },
    },
  };
});
