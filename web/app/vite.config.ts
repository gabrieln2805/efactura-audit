import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// relative base: the built site works from any folder (Cloudflare Pages root, a sub-path, or a local server)
export default defineConfig({
  base: "./",
  plugins: [react()],
  worker: { format: "es" },
  // Plotly is one lazily loaded chunk (~480 kB gzipped), fetched with the first chart
  build: { chunkSizeWarningLimit: 1600 },
  server: { host: "127.0.0.1", port: 5180, strictPort: true },
  preview: { host: "127.0.0.1", port: 5181, strictPort: true },
});
