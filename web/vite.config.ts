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
  optimizeDeps: {
    /**
     * MapLibre must not be pre-bundled.
     *
     * It spawns its GeoJSON/vector parser as a module worker from a URL
     * relative to its own entry (`new Worker(new URL("./maplibre-gl-worker.mjs",
     * import.meta.url), { type: "module" })`). Vite's dependency optimiser
     * rewrites the entry into `node_modules/.vite/deps/maplibre-gl.mjs` but
     * does not copy the sibling worker, so the worker request fails with
     * ERR_FAILED. The failure is silent: no MapLibre `error` event and no
     * console output. Every GeoJSON source then stays permanently unloaded —
     * `isSourceLoaded()` false, `querySourceFeatures()` empty — so the whole
     * risk overlay renders nothing while the raster basemap, which needs no
     * worker, draws normally.
     *
     * Excluding it makes Vite serve the real ESM from `node_modules`, where
     * the worker resolves as a sibling. The production build is unaffected:
     * Rollup understands the `new URL(..., import.meta.url)` worker idiom and
     * emits the chunk itself.
     */
    exclude: ["maplibre-gl"],
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
