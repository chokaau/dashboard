/**
 * Tests for useLogout hook (Epic 5 remaining).
 *
 * TDD: RED tests first. Covers:
 * - queryClient.clear() called on logout
 * - sessionStorage.clear() called
 * - Zustand store status reset to "all"
 * - signOut() called
 * - All operations happen before signOut resolves
 */
import { render, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockSignOut = vi.fn().mockResolvedValue(undefined);
const mockSetStatus = vi.fn();

vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => ({
    isAuthenticated: true,
    signOut: mockSignOut,
    getAccessToken: vi.fn().mockResolvedValue("tok"),
  }),
}));

vi.mock("@/stores/call-history-filters", () => ({
  useCallHistoryFilters: (selector: (s: { setStatus: typeof mockSetStatus }) => unknown) =>
    selector({ setStatus: mockSetStatus }),
}));

// ---------------------------------------------------------------------------
// Test component
// ---------------------------------------------------------------------------

import { useLogout } from "@/hooks/use-logout";

let capturedLogout: (() => Promise<void>) | null = null;

function TestComponent() {
  capturedLogout = useLogout();
  return null;
}

function renderHook(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <TestComponent />
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useLogout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedLogout = null;
    sessionStorage.clear();
  });

  it("clears the TanStack Query cache", async () => {
    const qc = new QueryClient();
    // Seed cache with data
    qc.setQueryData(["calls"], { calls: [], stats: {} });
    expect(qc.getQueryData(["calls"])).toBeDefined();

    const clearSpy = vi.spyOn(qc, "clear");
    renderHook(qc);

    await act(async () => {
      await capturedLogout!();
    });

    expect(clearSpy).toHaveBeenCalledTimes(1);
    expect(qc.getQueryData(["calls"])).toBeUndefined();
  });

  it("clears sessionStorage", async () => {
    sessionStorage.setItem("some-key", "some-value");
    expect(sessionStorage.getItem("some-key")).toBe("some-value");

    const qc = new QueryClient();
    renderHook(qc);

    await act(async () => {
      await capturedLogout!();
    });

    expect(sessionStorage.getItem("some-key")).toBeNull();
  });

  it("resets Zustand call history filter status to 'all'", async () => {
    const qc = new QueryClient();
    renderHook(qc);

    await act(async () => {
      await capturedLogout!();
    });

    expect(mockSetStatus).toHaveBeenCalledWith("all");
  });

  it("calls signOut", async () => {
    const qc = new QueryClient();
    renderHook(qc);

    await act(async () => {
      await capturedLogout!();
    });

    expect(mockSignOut).toHaveBeenCalledTimes(1);
  });

  it("clears cache before calling signOut", async () => {
    const qc = new QueryClient();
    const order: string[] = [];
    vi.spyOn(qc, "clear").mockImplementation(() => {
      order.push("clear");
    });
    mockSignOut.mockImplementationOnce(async () => {
      order.push("signOut");
    });

    renderHook(qc);

    await act(async () => {
      await capturedLogout!();
    });

    expect(order).toEqual(["clear", "signOut"]);
  });
});
