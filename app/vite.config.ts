import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The renderer is a plain SPA: one html, no routing, no proxying — it talks to the sidecar's
// loopback URL handed over by the preload, never to Vite's dev server.
export default defineConfig({
  plugins: [react()],
  root: "renderer",
  base: "./",
  // Pinned to IPv4 on purpose: left to its own devices Vite may bind ::1 (it did here), and then
  // anything that resolves `localhost` to 127.0.0.1 — some Chromium loads do — gets connection-refused
  // and a blank window. One stack, one URL, no resolution lottery.
  server: { host: "127.0.0.1", port: 5173, strictPort: true },
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
});
