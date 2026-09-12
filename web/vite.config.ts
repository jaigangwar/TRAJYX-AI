import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
// `vitest/config` rather than `vite` so the `test` block is typed.
import { defineConfig } from "vitest/config";

const resolvePath = (relative: string) => fileURLToPath(new URL(relative, import.meta.url));

/**
 * Map, charting and 3D libraries are large and change rarely. Splitting them
 * out keeps the dashboard shell cacheable across deploys, and keeps the
 * initial payload for text-heavy pages (violations, reports) small.
 */
const VENDOR_CHUNKS: Record<string, readonly string[]> = {
  maplibre: ["maplibre-gl"],
  charts: ["recharts", "d3-scale", "d3-shape", "d3-array", "victory-vendor"],
  three: ["three"],
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": resolvePath("./src"),
      // The generated domain contract is shared with the backend and mobile app.
      // Importing it rather than redeclaring types keeps the three in lockstep.
      "@shared": resolvePath("../shared/ts"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          for (const [chunk, packages] of Object.entries(VENDOR_CHUNKS)) {
            if (packages.some((name) => id.includes(`node_modules/${name}`))) return chunk;
          }
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      reportsDirectory: "../coverage/web",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/test/**", "src/**/*.d.ts", "src/main.tsx"],
    },
  },
});
