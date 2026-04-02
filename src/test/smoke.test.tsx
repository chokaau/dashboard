/**
 * Smoke test — App renders without throwing.
 * Story 1.10 — TDD red phase. Fails until App.tsx exists.
 */
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import App from "../App";

// Mock aws-amplify to avoid real configuration in tests
vi.mock("aws-amplify", () => ({
  Amplify: { configure: vi.fn() },
}));

vi.mock("aws-amplify/auth", () => ({
  signIn: vi.fn(),
  signOut: vi.fn(),
  getCurrentUser: vi.fn().mockRejectedValue(new Error("not authenticated")),
  fetchAuthSession: vi.fn().mockResolvedValue({ tokens: undefined }),
  Hub: { listen: vi.fn(() => () => {}) },
}));

// Use a simple null auth context for the smoke test
vi.mock("../adapters/cognito-auth-provider", () => ({
  CognitoAuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

describe("App smoke test", () => {
  it("renders without throwing", () => {
    expect(() =>
      render(
        <MemoryRouter>
          <App />
        </MemoryRouter>
      )
    ).not.toThrow();
  });
});
