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
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
});
