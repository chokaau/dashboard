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

vi.mock("@chokaau/ui", () => ({
  Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={`animate-pulse ${className ?? ""}`} />
  ),
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
      expect(screen.getByText(/18 days/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /start subscription|upgrade/i })).toBeInTheDocument();
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
      expect(screen.getByText(/3 days/i)).toBeInTheDocument();
    });
    // Warning indicator
    expect(screen.getByText(/ending|expir/i)).toBeInTheDocument();
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
