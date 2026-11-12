import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  // Same place as the other SLAI applications: <app>/dist, served by `python -m applications.slaifi`.
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
});
