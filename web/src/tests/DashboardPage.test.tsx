/**
 * Tests for story-5-4: DashboardPage.
 *
 * TDD: RED tests written first. Tests cover:
 * - Shows 4 stat cards with data.stats values
 * - Shows callback leads in NeedsCallbackPanel
 * - Shows skeleton when isLoading
 * - Shows PageError on query error with refetch button
 * - CallCard onClick navigates to /calls/{id}
 *
 * NOTE: @choka/ui components are mocked to avoid cross-package bundler
 * complexity in unit tests. Integration tests cover the full render.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mock @choka/ui components (avoids cross-package bundler issues in unit tests)
// ---------------------------------------------------------------------------

vi.mock("@choka/ui/src/components/custom/DashboardStatCard", () => ({
  DashboardStatCard: ({
    label,
    value,
    isLoading,
  }: {
    label: string;
    value?: string;
    isLoading?: boolean;
  }) => (
    <div data-testid="stat-card">
      <span>{label}</span>
      {isLoading ? (
        <div className="animate-pulse" />
      ) : (
        <span data-testid="stat-value">{value}</span>
      )}
    </div>
  ),
}));

vi.mock("@choka/ui/src/components/custom/NeedsCallbackPanel", () => ({
  NeedsCallbackPanel: ({
    calls,
    isLoading,
  }: {
    calls: Array<{ callerName: string }>;
    isLoading?: boolean;
  }) => (
    <div data-testid="callback-panel">
      {isLoading ? (
        <div className="animate-pulse" />
      ) : (
        calls.map((c, i) => (
          <div key={i} data-testid="callback-lead">
            {c.callerName}
          </div>
        ))
      )}
    </div>
  ),
}));

vi.mock("@choka/ui/src/components/custom/CallCard", () => ({
  CallCard: ({
    callerName,
    onClick,
  }: {
    callerName: string;
    onClick?: () => void;
  }) => (
    <div
      data-testid="call-card"
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick?.()}
    >
      {callerName}
    </div>
  ),
}));

vi.mock("@choka/ui/src/components/primitives/PageError", () => ({
  PageError: ({
    title,
    description,
    onRetry,
  }: {
    title?: string;
    description: string;
    onRetry: () => void;
  }) => (
    <div role="alert">
      {title && <h2>{title}</h2>}
      <p>{description}</p>
      <button type="button" onClick={onRetry}>
        Try again
      </button>
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock useCallEvents — no-op in unit tests (SSE tested separately)
vi.mock("@/hooks/use-call-events", () => ({
  useCallEvents: () => undefined,
}));

// Mock apiFetch
// ---------------------------------------------------------------------------
const mockApiFetch = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      message: string,
      public code?: string
    ) {
      super(message);
      this.name = "ApiError";
    }
  },
}));

// Mock auth context
vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => ({
    isLoaded: true,
    isAuthenticated: true,
    user: { username: "owner", tenantSlug: "acme" },
    signOut: vi.fn(),
    getAccessToken: vi.fn().mockResolvedValue("tok"),
  }),
}));

import { DashboardPage } from "@/pages/DashboardPage";

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const sampleCallsResponse = {
  calls: [
    {
      id: "call-1",
      callerName: "Alice Smith",
      callerPhone: "+61412000001",
      intent: "quote",
      summary: "Needs quote for switchboard upgrade",
      timestamp: "Today 9:30 AM",
      duration: "2m 15s",
      needsCallback: true,
      urgent: false,
    },
    {
      id: "call-2",
      callerName: "Bob Jones",
      callerPhone: "+61412000002",
      intent: "info",
      summary: "Asked about service areas",
      timestamp: "Today 8:00 AM",
      duration: "1m 05s",
      needsCallback: false,
      urgent: false,
    },
    {
      id: "call-3",
      callerName: "Carol White",
      callerPhone: "+61412000003",
      intent: "urgent",
      summary: "Emergency — power outage",
      timestamp: "Yesterday 6:00 PM",
      duration: "3m 45s",
      needsCallback: true,
      urgent: true,
    },
  ],
  stats: {
    totalToday: 2,
    needsCallback: 2,
    total: 3,
  },
  pagination: { page: 1, pageSize: 20, total: 3 },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
}

function renderDashboard() {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/calls/:id" element={<div>CallDetail</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows skeleton when loading", async () => {
    mockApiFetch.mockReturnValue(new Promise(() => {}));

    const { container } = renderDashboard();

    await waitFor(() => {
      expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
    });
  });

  it("shows PageError on query error", async () => {
    mockApiFetch.mockRejectedValue(new Error("Network error"));

    renderDashboard();

    await waitFor(
      () => {
        expect(
          screen.getByRole("button", { name: /try again/i })
        ).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });

  it("shows 4 stat cards with correct labels", async () => {
    mockApiFetch.mockResolvedValue(sampleCallsResponse);

    renderDashboard();

    // Wait until data has loaded (stat-value elements appear)
    await waitFor(() => {
      expect(screen.getAllByTestId("stat-value").length).toBeGreaterThan(0);
    });

    // All 4 stat card labels
    expect(screen.getByText("Calls today")).toBeInTheDocument();
    expect(screen.getByText("Need callback")).toBeInTheDocument();
    expect(screen.getByText("Total calls")).toBeInTheDocument();
    expect(screen.getByText("Avg duration")).toBeInTheDocument();

    // Stats values
    const statValues = screen.getAllByTestId("stat-value");
    const valueTexts = statValues.map((el) => el.textContent);
    expect(valueTexts).toContain("3"); // total
    expect(valueTexts).toContain("2"); // totalToday or needsCallback
  });

  it("shows NeedsCallbackPanel with callback calls", async () => {
    mockApiFetch.mockResolvedValue(sampleCallsResponse);

    renderDashboard();

    await waitFor(() => {
      // Alice and Carol appear in callback-panel (may also appear in recent calls)
      const callbackLeads = screen.getAllByTestId("callback-lead");
      const names = callbackLeads.map((el) => el.textContent);
      expect(names).toContain("Alice Smith");
      expect(names).toContain("Carol White");
    });
  });

  it("shows recent calls list", async () => {
    mockApiFetch.mockResolvedValue(sampleCallsResponse);

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText("Bob Jones")).toBeInTheDocument();
    });
  });

  it("clicking a call card navigates to /calls/{id}", async () => {
    mockApiFetch.mockResolvedValue(sampleCallsResponse);

    renderDashboard();

    await waitFor(() => {
      expect(screen.getAllByText("Bob Jones").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getAllByText("Bob Jones")[0]);

    await waitFor(() => {
      expect(screen.getByText("CallDetail")).toBeInTheDocument();
    });
  });
});
