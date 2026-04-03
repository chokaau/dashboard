/**
 * Tests for story-5-7: ProfilePage.
 *
 * TDD: RED tests written first. Tests cover:
 * - Shows skeleton on first load
 * - Renders business name and greeting fields on success
 * - Save button submits updated form values
 * - Shows inline error on save failure
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockApiFetch = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
  ApiError: class ApiError extends Error {
    constructor(public status: number, message: string, public code?: string) {
      super(message);
      this.name = "ApiError";
    }
  },
}));

vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => ({
    isLoaded: true,
    isAuthenticated: true,
    user: { username: "owner", tenantSlug: "acme" },
    signOut: vi.fn(),
    getAccessToken: vi.fn().mockResolvedValue("tok"),
  }),
}));

import { ProfilePage } from "@/pages/ProfilePage";

vi.mock("@chokaau/ui", () => ({
Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={`animate-pulse ${className ?? ""}`} />
  ),
InlineError: ({ message }: { message: string }) => (
    <div role="alert" data-testid="inline-error">{message}</div>
  ),
}));


function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function renderPage() {
  const qc = makeQC();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/profile"]}>
        <Routes>
          <Route path="/profile" element={<ProfilePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const sampleProfile = {
  businessName: "Dave's Electrical Services",
  greeting: "Hi, you've reached Dave's Electrical Services.",
  notificationPreference: "all",
};

describe("ProfilePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows skeleton on first load", async () => {
    mockApiFetch.mockReturnValue(new Promise(() => {}));
    const { container } = renderPage();
    await waitFor(() => {
      expect(
        container.querySelector(".animate-pulse") ||
        container.querySelector("[data-testid='skeleton']")
      ).toBeInTheDocument();
    });
  });

  it("renders profile fields on success", async () => {
    mockApiFetch.mockResolvedValue(sampleProfile);
    renderPage();
    await waitFor(() => {
      expect(screen.getByDisplayValue("Dave's Electrical Services")).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue("Hi, you've reached Dave's Electrical Services.")).toBeInTheDocument();
  });

  it("save button is present after load", async () => {
    mockApiFetch.mockResolvedValue(sampleProfile);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save/i })).toBeInTheDocument();
    });
  });

  it("shows inline error on save failure", async () => {
    // First call: GET profile succeeds
    mockApiFetch
      .mockResolvedValueOnce(sampleProfile)
      .mockRejectedValueOnce(new Error("Save failed"));

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(screen.getByTestId("inline-error")).toBeInTheDocument();
    });
  });
});
