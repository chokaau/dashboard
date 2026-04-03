import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      thresholds: {
        lines: 80,
        branches: 70,
        // Critical path overrides: adapters and core lib files require 95% line coverage
        "src/adapters/**": {
          lines: 95,
        },
        "src/lib/api-client.ts": {
          lines: 95,
        },
        "src/lib/query-client.ts": {
          lines: 95,
        },
      },
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/test/**",
        "src/main.tsx",
        "src/vite-env.d.ts",
        "src/adapters/cognito-auth-provider.tsx",
        // Stale placeholder stubs superseded by src/pages/auth/* implementations
        "src/pages/SignInPage.tsx",
        "src/pages/SignUpPage.tsx",
        "src/pages/ConfirmPage.tsx",
      ],
    },
  },
  resolve: {
    alias: [
      // Local dev fallback: resolves @chokaau/ui to storybook source when
      // the package isn't installed from GitHub Packages. CI installs it
      // via NODE_AUTH_TOKEN so this alias is unused there.
      {
        find: "@chokaau/ui",
        replacement: resolve(__dirname, "../../storybook/src/index.ts"),
      },
      { find: /^@\/(.*)/, replacement: resolve(__dirname, "./src/$1") },
    ],
  },
});
