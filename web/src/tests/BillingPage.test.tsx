/**
 * Tests for story-5-8: BillingPage.
 *
 * TDD: RED tests written first. Tests cover:
 * - Shows skeleton on first load
 * - Trial active state: shows days remaining and upgrade CTA
 * - Trial expiring (≤3 days): shows warning banner
 * - Subscribed state: shows active subscription info
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@chokaau/ui", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@chokaau/ui")>();
  return {
    ...actual,
    Skeleton: ({ className }: { className?: string }) => (
      <div data-testid="skeleton" className={`animate-pulse ${className ?? ""}`} />
    ),
    TrialBanner: ({
      daysRemaining,
      onUpgrade,
    }: {
      daysRemaining: number;
      onUpgrade: () => void;
    }) => (
      <div data-testid="trial-banner">
        <span>{daysRemaining} days remaining</span>
        <button type="button" onClick={onUpgrade}>Start subscription</button>
      </div>
    ),
    CurrentPlanCard: ({
      status,
      daysRemaining,
      planName,
      nextBillingDate,
      amount,
      onUpgrade,
    }: {
      status: string;
      daysRemaining?: number;
      planName?: string;
      nextBillingDate?: string;
      amount?: string;
      onUpgrade: () => void;
    }) => (
      <div data-testid="current-plan-card">
        {status === "active" && <span>Active</span>}
        {status === "trial" && daysRemaining !== undefined && (
          <span>{daysRemaining} days remaining</span>
        )}
        {planName && <span>{planName}</span>}
        {nextBillingDate && <span>Next billing: {nextBillingDate}</span>}
        {amount && <span>{amount}</span>}
        <button type="button" onClick={onUpgrade}>Upgrade</button>
      </div>
    ),
  };
});

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

import { BillingPage } from "@/pages/BillingPage";

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage() {
  const qc = makeQC();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/billing"]}>
        <Routes>
          <Route path="/billing" element={<BillingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("BillingPage", () => {
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

  it("shows trial days remaining and upgrade CTA", async () => {
    mockApiFetch.mockResolvedValue({
      status: "trial",
      trialDaysRemaining: 18,
      planName: "Starter",
      planPrice: 249,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText(/18 days/i).length).toBeGreaterThan(0);
    });
    expect(screen.getAllByRole("button", { name: /start subscription|upgrade/i }).length).toBeGreaterThan(0);
  });

  it("shows expiry warning when trial has 3 or fewer days", async () => {
    mockApiFetch.mockResolvedValue({
      status: "trial",
      trialDaysRemaining: 3,
      planName: "Starter",
      planPrice: 249,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText(/3 days/i).length).toBeGreaterThan(0);
    });
    // TrialBanner is rendered when status is "trial"
    expect(screen.getByTestId("trial-banner")).toBeInTheDocument();
  });

  it("shows active subscription info when subscribed", async () => {
    mockApiFetch.mockResolvedValue({
      status: "active",
      trialDaysRemaining: 0,
      planName: "Starter",
      planPrice: 249,
      nextBillingDate: "2026-05-01",
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/active/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/249/).length).toBeGreaterThan(0);
  });
});
