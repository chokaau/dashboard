import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";
import { existsSync } from "fs";
import type { Plugin } from "vite";

const dashboardSrc = resolve(__dirname, "./src");
const storybookSrc = resolve(__dirname, "../storybook/src");

/**
 * Handles all @/ and @choka/ui/src/... alias resolution.
 *
 * Key insight: vite's built-in alias plugin (vite:pre-alias) always runs
 * before custom plugin resolveId hooks, even with enforce:"pre".
 * Solution: do NOT put "@" in resolve.alias — handle it entirely here
 * via the "load" hook which runs after module id resolution.
 *
 * Actually the correct hook order for beating vite's alias is to use
 * buildStart + configResolved to inject our alias before vite:pre-alias.
 *
 * Simplest reliable approach: override resolve.alias at config time,
 * intercept via the "resolveId" hook by NOT having "@" in the static alias
 * array (so vite's alias plugin doesn't touch @/).
 */
function chokaAliasPlugin(): Plugin {
  return {
    name: "choka-alias",
    enforce: "pre",
    resolveId(source, importer) {
      // @choka/ui/src/X → storybook/src/X
      const uiMatch = source.match(/^@choka\/ui\/src\/(.+)/);
      if (uiMatch) {
        const base = resolve(storybookSrc, uiMatch[1]);
        for (const ext of [".tsx", ".ts", ".jsx", ".js"]) {
          if (existsSync(base + ext)) return base + ext;
        }
        return base;
      }

      if (!source.startsWith("@/")) return null;

      // @/X from storybook source → storybook/src/X
      if (
        importer &&
        (importer.startsWith(storybookSrc) ||
          importer.includes("/storybook/src/"))
      ) {
        const base = resolve(storybookSrc, source.slice(2));
        for (const ext of [".tsx", ".ts", ".jsx", ".js"]) {
          if (existsSync(base + ext)) return base + ext;
        }
        return base;
      }

      // @/X → dashboard/src/X (for dashboard source files)
      const base = resolve(dashboardSrc, source.slice(2));
      for (const ext of [".tsx", ".ts", ".jsx", ".js"]) {
        if (existsSync(base + ext)) return base + ext;
      }
      return base;
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), chokaAliasPlugin()],
  resolve: {
    dedupe: ["react", "react-dom", "lucide-react"],
    alias: [
      // @choka/ui/src/... → storybook/src/... (for tsc + IDEs)
      {
        find: /^@choka\/ui\/src\/(.*)/,
        replacement: `${storybookSrc}/$1`,
      },
      // NOTE: "@" is intentionally NOT in alias array —
      // chokaAliasPlugin handles all @/ resolution so it can
      // distinguish storybook vs dashboard source files.
    ],
  },
});
