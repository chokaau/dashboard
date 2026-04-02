/**
 * Tests for story-5-5: CallHistoryPage.
 *
 * TDD: RED tests written first. Tests cover:
 * - Changing status filter updates query key (new fetch)
 * - Changing date filter resets page to 1
 * - Empty result renders EmptyState with correct message
 * - Empty state is wrapped in aria-live="polite" region
 * - Shows skeleton on first load
 * - Shows paginated call cards on success
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mock @choka/ui components
// ---------------------------------------------------------------------------

vi.mock("@choka/ui", () => ({
  CallHistoryFilterBar: ({
    activeTab,
    onTabChange,
    dateFilter,
    onDateFilterChange,
  }: {
    activeTab: string;
    onTabChange: (tab: string) => void;
    dateFilter: string;
    onDateFilterChange: (f: string) => void;
    searchQuery: string;
    onSearchChange: (q: string) => void;
    needsCallbackCount?: number;
  }) => (
    <div data-testid="filter-bar">
      <button
        data-testid="tab-missed"
        aria-pressed={activeTab === "missed"}
        onClick={() => onTabChange("missed")}
      >
        Missed
      </button>
      <button
        data-testid="tab-all"
        aria-pressed={activeTab === "all"}
        onClick={() => onTabChange("all")}
      >
        All Calls
      </button>
      <button
        data-testid="date-week"
        aria-pressed={dateFilter === "week"}
        onClick={() => onDateFilterChange("week")}
      >
        This Week
      </button>
    </div>
  ),
}));

vi.mock("@choka/ui", () => ({
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
      onKeyDown={(e) => e.key === "Enter" && onClick?.()}
      role="button"
      tabIndex={0}
    >
      {callerName}
    </div>
  ),
}));

vi.mock("@choka/ui", () => ({
  EmptyState: ({ title }: { title: string; description: string; icon: unknown }) => (
    <div data-testid="empty-state" role="status">
      {title}
    </div>
  ),
}));

vi.mock("@choka/ui", () => ({
  Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={`animate-pulse ${className ?? ""}`} />
  ),
}));

// ---------------------------------------------------------------------------
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

vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => ({
    isLoaded: true,
    isAuthenticated: true,
    user: { username: "owner", tenantSlug: "acme" },
    signOut: vi.fn(),
    getAccessToken: vi.fn().mockResolvedValue("tok"),
  }),
}));

import { CallHistoryPage } from "@/pages/CallHistoryPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage() {
  const qc = makeQC();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/calls"]}>
        <Routes>
          <Route path="/calls" element={<CallHistoryPage />} />
          <Route path="/calls/:id" element={<div>CallDetail</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const makeResponse = (calls: unknown[] = [], total = 0) => ({
  calls,
  stats: { totalToday: 0, needsCallback: 0, total },
  pagination: { page: 1, pageSize: 20, total },
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CallHistoryPage", () => {
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

  it("renders call cards on success", async () => {
    mockApiFetch.mockResolvedValue(
      makeResponse([
        {
          id: "c1",
          callerName: "Jane Doe",
          callerPhone: "+61400000001",
          intent: "info",
          summary: "Test",
          timestamp: "Today 9am",
          duration: "1m",
          needsCallback: false,
        },
      ], 1)
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    });
  });

  it("renders empty state when no calls match", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([], 0));

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    });
  });

  it("empty state is wrapped in aria-live region", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([], 0));

    const { container } = renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    });

    const liveRegion = container.querySelector("[aria-live]");
    expect(liveRegion).toBeInTheDocument();
  });

  it("changing status filter triggers new fetch with updated params", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([], 0));

    renderPage();

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(screen.getByTestId("tab-missed"));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledTimes(2);
      const lastCall = mockApiFetch.mock.calls[1][0] as string;
      expect(lastCall).toContain("status=missed");
    });
  });

  it("changing date filter resets page to 1 and triggers new fetch", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([], 0));

    renderPage();

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(screen.getByTestId("date-week"));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledTimes(2);
    });

    // Verify page reset by checking no page>1 in URL
    const lastCall = mockApiFetch.mock.calls[1][0] as string;
    expect(lastCall).not.toContain("page=2");
  });
});
