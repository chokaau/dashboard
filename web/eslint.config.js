// eslint.config.js — ESLint v9 flat config (story-4-3 Epic 7)
//
// Applies jsx-a11y/recommended to all TS/TSX source files.
// Uses @typescript-eslint/parser so ESLint can parse TypeScript syntax.

import tsParser from "@typescript-eslint/parser";
import jsxA11y from "eslint-plugin-jsx-a11y";

export default [
  // Apply jsx-a11y recommended rules to all TS/TSX source files
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...jsxA11y.configs.recommended.rules,
    },
    settings: {
      // Treat custom components the same as their HTML counterparts
      "jsx-a11y": {
        components: {
          Button: "button",
          Input: "input",
          Label: "label",
        },
      },
    },
  },
  // Ignore generated/test infrastructure files
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "coverage/**",
      "src/vite-env.d.ts",
    ],
  },
];
