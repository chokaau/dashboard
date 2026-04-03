/**
 * Tests for dashboard-10: ActivationBanner integration on DashboardPage.
 *
 * TDD: RED tests written first. Tests cover:
 * - Banner shown when billing returns activationStatus=pending
 * - Banner not shown when activationStatus=none
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/hooks/use-call-events", () => ({
  useCallEvents: () => undefined,
}));

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

vi.mock("@chokaau/ui", () => ({
  DashboardStatCard: ({ label }: { label: string }) => (
    <div data-testid="stat-card">{label}</div>
  ),
  NeedsCallbackPanel: () => <div data-testid="callback-panel" />,
  CallCard: () => <div data-testid="call-card" />,
  PageError: ({ description, onRetry }: { description: string; onRetry: () => void }) => (
    <div role="alert">
      <p>{description}</p>
      <button type="button" onClick={onRetry}>Try again</button>
    </div>
  ),
}));

import { DashboardPage } from "@/pages/DashboardPage";

const emptyCalls = {
  calls: [],
  stats: { totalToday: 0, needsCallback: 0, total: 0 },
  pagination: { page: 1, pageSize: 20, total: 0 },
};

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderDashboard() {
  const qc = makeQC();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DashboardPage — ActivationBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows activation banner when billing returns activationStatus=pending", async () => {
    // /api/calls returns empty data
    mockApiFetch.mockImplementation((path: string) => {
      if (path === "/api/calls") return Promise.resolve(emptyCalls);
      if (path === "/api/billing")
        return Promise.resolve({
          plan: "trial",
          trialDaysRemaining: 14,
          trialEndDate: "2026-04-18",
          isTrialExpired: false,
          activationStatus: "pending",
          product: "voice",
        });
      return Promise.reject(new Error("unexpected"));
    });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByText(/being reviewed/i)).toBeInTheDocument();
  });

  it("does not show activation banner when activationStatus is none", async () => {
    mockApiFetch.mockImplementation((path: string) => {
      if (path === "/api/calls") return Promise.resolve(emptyCalls);
      if (path === "/api/billing")
        return Promise.resolve({
          plan: "trial",
          trialDaysRemaining: 14,
          trialEndDate: "2026-04-18",
          isTrialExpired: false,
          activationStatus: "none",
          product: "",
        });
      return Promise.reject(new Error("unexpected"));
    });

    renderDashboard();

    // Wait for calls query to settle
    await waitFor(() => {
      expect(screen.getAllByTestId("stat-card").length).toBeGreaterThan(0);
    });

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
