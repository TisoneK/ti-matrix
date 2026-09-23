import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The renderer is a plain SPA: one html, no routing, no proxying — it talks to the sidecar's
// loopback URL handed over by the preload, never to Vite's dev server.
export default defineConfig({
  plugins: [react()],
  root: "renderer",
  base: "./",
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
});
