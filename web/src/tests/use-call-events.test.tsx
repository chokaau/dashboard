/**
 * Tests for useCallEvents hook (story-4-2 / Epic 7).
 *
 * TDD: RED tests first.
 * Covers:
 * - call_completed event triggers queryClient.invalidateQueries
 * - ping event does not invalidate queries
 * - EventSource error triggers reconnect scheduling
 * - 5 consecutive errors with no success enables polling fallback
 * - Logout (isAuthenticated=false) closes connection
 * - Fresh token fetched on each reconnect
 * - getAccessToken failure calls signOut and stops reconnecting
 */
import {
  render,
  act,
  waitFor,
} from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mock EventSource
// ---------------------------------------------------------------------------

type ESListener = (event: MessageEvent | Event) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  withCredentials: boolean;
  private listeners: Map<string, ESListener[]> = new Map();
  onerror: ((e: Event) => void) | null = null;
  closed = false;

  constructor(url: string, init?: { withCredentials?: boolean }) {
    this.url = url;
    this.withCredentials = init?.withCredentials ?? false;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: ESListener) {
    const arr = this.listeners.get(type) ?? [];
    arr.push(listener);
    this.listeners.set(type, arr);
  }

  dispatchNamedEvent(type: string, data?: string) {
    const evt = Object.assign(new Event(type), { data: data ?? "" });
    for (const fn of this.listeners.get(type) ?? []) {
      fn(evt as unknown as MessageEvent);
    }
  }

  triggerError() {
    if (this.onerror) this.onerror(new Event("error"));
  }

  close() {
    this.closed = true;
  }
}

vi.stubGlobal("EventSource", MockEventSource);

// ---------------------------------------------------------------------------
// Mock auth
// ---------------------------------------------------------------------------

const mockGetAccessToken = vi.fn().mockResolvedValue("test-token");
const mockSignOut = vi.fn();
let mockIsAuthenticated = true;

vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => ({
    get isAuthenticated() { return mockIsAuthenticated; },
    getAccessToken: mockGetAccessToken,
    signOut: mockSignOut,
  }),
}));

// ---------------------------------------------------------------------------
// Test component
// ---------------------------------------------------------------------------

import { useCallEvents } from "@/hooks/use-call-events";

function TestComponent() {
  useCallEvents();
  return null;
}

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderHook(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <TestComponent />
    </QueryClientProvider>
  );
}

// Wait for all pending microtasks
function flushPromises() {
  return new Promise<void>((resolve) => setTimeout(resolve, 0));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useCallEvents", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockEventSource.instances = [];
    mockIsAuthenticated = true;
    mockGetAccessToken.mockResolvedValue("test-token");
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it("opens EventSource to /api/events?token= when authenticated", async () => {
    const qc = makeQC();
    renderHook(qc);

    await act(flushPromises);

    expect(MockEventSource.instances.length).toBe(1);
    expect(MockEventSource.instances[0].url).toContain("/api/events?token=test-token");
  });

  it("does not open EventSource when not authenticated", async () => {
    mockIsAuthenticated = false;
    const qc = makeQC();
    renderHook(qc);

    await act(flushPromises);

    expect(MockEventSource.instances.length).toBe(0);
  });

  it("invalidates ['calls'] query on call_completed event", async () => {
    const qc = makeQC();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    renderHook(qc);

    await act(flushPromises);
    const es = MockEventSource.instances[0];

    await act(async () => {
      es.dispatchNamedEvent("call_completed", '{"callId":"cid-1"}');
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["calls"] });
  });

  it("does not invalidate queries on ping event", async () => {
    const qc = makeQC();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    renderHook(qc);

    await act(flushPromises);
    const es = MockEventSource.instances[0];

    await act(async () => {
      es.dispatchNamedEvent("ping");
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("closes connection on unmount", async () => {
    const qc = makeQC();
    const { unmount } = renderHook(qc);

    await act(flushPromises);
    const es = MockEventSource.instances[0];

    unmount();

    expect(es.closed).toBe(true);
  });

  it("calls signOut when getAccessToken throws NotAuthorizedException", async () => {
    mockGetAccessToken.mockRejectedValueOnce(new Error("NotAuthorizedException"));

    const qc = makeQC();
    renderHook(qc);

    await act(flushPromises);

    expect(mockSignOut).toHaveBeenCalledTimes(1);
    // No EventSource opened since token fetch failed immediately
    expect(MockEventSource.instances.length).toBe(0);
  });

  it("fetches a fresh token on reconnect", async () => {
    mockGetAccessToken
      .mockResolvedValueOnce("token-1")
      .mockResolvedValueOnce("token-2");

    // Use real timers but patch setTimeout to fire immediately
    const originalSetTimeout = globalThis.setTimeout;
    vi.spyOn(globalThis, "setTimeout").mockImplementation(
      (fn: TimerHandler, _delay?: number) => {
        // Run callback on next microtask (no actual delay)
        void Promise.resolve().then(() => {
          if (typeof fn === "function") fn();
        });
        return 0 as unknown as ReturnType<typeof setTimeout>;
      }
    );

    const qc = makeQC();
    renderHook(qc);

    await act(flushPromises);
    expect(MockEventSource.instances.length).toBe(1);
    expect(MockEventSource.instances[0].url).toContain("token-1");

    await act(async () => {
      MockEventSource.instances[0].triggerError();
      await flushPromises();
    });

    await act(flushPromises);

    expect(MockEventSource.instances.length).toBe(2);
    expect(MockEventSource.instances[1].url).toContain("token-2");

    vi.restoreAllMocks();
    void originalSetTimeout; // keep reference to avoid lint warning
  });

  it("enables 30s polling fallback after 5 errors with no success", async () => {
    vi.useFakeTimers();

    const qc = makeQC();
    const setDefaultsSpy = vi.spyOn(qc, "setQueryDefaults");

    // Make tokens always resolve
    mockGetAccessToken.mockResolvedValue("tok");
    renderHook(qc);

    await act(() => Promise.resolve());

    // Trigger 5 consecutive errors
    for (let i = 0; i < 5; i++) {
      const last = MockEventSource.instances[MockEventSource.instances.length - 1];
      await act(async () => {
        last.triggerError();
        // Advance past backoff for this attempt (2^i seconds)
        vi.advanceTimersByTime(60_000);
        await Promise.resolve();
      });
    }

    expect(setDefaultsSpy).toHaveBeenCalledWith(
      ["calls"],
      expect.objectContaining({ refetchInterval: 30_000 })
    );
    vi.useRealTimers();
  });

  it("resets polling fallback after successful ping", async () => {
    const qc = makeQC();
    const setDefaultsSpy = vi.spyOn(qc, "setQueryDefaults");
    renderHook(qc);

    await act(flushPromises);
    const es = MockEventSource.instances[0];

    await act(async () => {
      es.dispatchNamedEvent("ping");
    });

    // Should clear any refetchInterval
    expect(setDefaultsSpy).toHaveBeenCalledWith(
      ["calls"],
      expect.objectContaining({ refetchInterval: undefined })
    );
  });
});
