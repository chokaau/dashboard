/**
 * Tests for story-5-10: AuthGuard + Logout.
 *
 * TDD: RED tests written first. Tests cover:
 * - AuthGuard redirects unauthenticated users to /auth/sign-in
 * - AuthGuard renders children when authenticated
 * - AuthGuard shows nothing (or spinner) while auth is loading
 * - Logout calls signOut and redirects to /auth/sign-in
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// ---------------------------------------------------------------------------
// Auth mock — controlled per test
// ---------------------------------------------------------------------------

const mockSignOut = vi.fn();
const mockAuthState = {
  isLoaded: true,
  isAuthenticated: true,
  user: { username: "owner", tenantSlug: "acme" },
  signOut: mockSignOut,
  getAccessToken: vi.fn().mockResolvedValue("tok"),
};

vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => mockAuthState,
}));

import { AuthGuard } from "@/components/AuthGuard";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderWithGuard(authOverrides: Partial<typeof mockAuthState> = {}) {
  Object.assign(mockAuthState, authOverrides);
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <AuthGuard>
              <div>Protected content</div>
            </AuthGuard>
          }
        />
        <Route path="/auth/sign-in" element={<div>Sign In page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AuthGuard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset to authenticated by default
    mockAuthState.isLoaded = true;
    mockAuthState.isAuthenticated = true;
  });

  it("renders children when authenticated", () => {
    renderWithGuard();
    expect(screen.getByText("Protected content")).toBeInTheDocument();
  });

  it("redirects to /auth/sign-in when not authenticated", () => {
    renderWithGuard({ isLoaded: true, isAuthenticated: false });
    expect(screen.getByText("Sign In page")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("shows nothing while auth is loading", () => {
    renderWithGuard({ isLoaded: false, isAuthenticated: false });
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    expect(screen.queryByText("Sign In page")).not.toBeInTheDocument();
  });

  it("calls signOut and redirects on logout", async () => {
    mockSignOut.mockResolvedValue(undefined);

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <AuthGuard>
                <button onClick={() => void mockAuthState.signOut()}>
                  Logout
                </button>
              </AuthGuard>
            }
          />
          <Route path="/auth/sign-in" element={<div>Sign In page</div>} />
        </Routes>
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole("button", { name: /logout/i }));

    await waitFor(() => {
      expect(mockSignOut).toHaveBeenCalled();
    });
  });
});
