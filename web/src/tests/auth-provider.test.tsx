/**
 * Tests for story-5-2: CognitoAuthProvider.
 *
 * TDD: RED tests written first. Tests cover:
 * - Empty VITE_COGNITO_USER_POOL_ID renders ConfigurationError
 * - Empty VITE_COGNITO_CLIENT_ID renders ConfigurationError
 * - Valid config renders children without ConfigurationError
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock aws-amplify
vi.mock("aws-amplify", () => ({
  Amplify: { configure: vi.fn() },
}));

vi.mock("aws-amplify/auth", () => ({
  signIn: vi.fn(),
  signOut: vi.fn(),
  getCurrentUser: vi.fn().mockRejectedValue(new Error("not authenticated")),
  fetchAuthSession: vi.fn().mockResolvedValue({ tokens: undefined }),
}));

vi.mock("aws-amplify/utils", () => ({
  Hub: { listen: vi.fn(() => () => {}) },
}));

describe("CognitoAuthProvider", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("renders ConfigurationError when VITE_COGNITO_USER_POOL_ID is empty", async () => {
    // Patch import.meta.env
    vi.stubEnv("VITE_COGNITO_USER_POOL_ID", "");
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "test-client-id");

    const { CognitoAuthProvider } = await import(
      "@/adapters/cognito-auth-provider"
    );

    render(
      <CognitoAuthProvider>
        <div>child content</div>
      </CognitoAuthProvider>
    );

    expect(
      screen.getByText(/configuration error/i)
    ).toBeInTheDocument();
    expect(screen.queryByText("child content")).not.toBeInTheDocument();
  });

  it("renders ConfigurationError when VITE_COGNITO_CLIENT_ID is empty", async () => {
    vi.stubEnv("VITE_COGNITO_USER_POOL_ID", "us-east-1_testpool");
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "");

    const { CognitoAuthProvider } = await import(
      "@/adapters/cognito-auth-provider"
    );

    render(
      <CognitoAuthProvider>
        <div>child content</div>
      </CognitoAuthProvider>
    );

    expect(
      screen.getByText(/configuration error/i)
    ).toBeInTheDocument();
    expect(screen.queryByText("child content")).not.toBeInTheDocument();
  });

  it("renders children when both env vars are set", async () => {
    vi.stubEnv("VITE_COGNITO_USER_POOL_ID", "us-east-1_testpool");
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "test-client-id");

    const { CognitoAuthProvider } = await import(
      "@/adapters/cognito-auth-provider"
    );

    render(
      <CognitoAuthProvider>
        <div>child content</div>
      </CognitoAuthProvider>
    );

    expect(screen.getByText("child content")).toBeInTheDocument();
    expect(screen.queryByText(/configuration error/i)).not.toBeInTheDocument();
  });
});
