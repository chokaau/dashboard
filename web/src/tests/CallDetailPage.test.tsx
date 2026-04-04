/**
 * Tests for story-5-6: CallDetailPage.
 *
 * TDD: RED tests written first. Tests cover:
 * - Shows skeleton on first load
 * - Renders call details on success (caller name, summary, timestamp, duration)
 * - Shows PageError on fetch failure with retry button
 * - Back button navigates to /calls
 * - Needs-callback badge visible when needsCallback is true
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mock @chokaau/ui components
// ---------------------------------------------------------------------------

vi.mock("@chokaau/ui", () => ({
  Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={`animate-pulse ${className ?? ""}`} />
  ),
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
      <button type="button" onClick={onRetry}>Try again</button>
    </div>
  ),
  CallDetailActionBar: ({
    phone,
    handled,
    onCallback,
    onMarkHandled,
  }: {
    phone: string;
    handled: boolean;
    onCallback: (phone: string) => void;
    onMarkHandled: (handled: boolean) => void;
  }) => (
    <div data-testid="action-bar">
      <button type="button" onClick={() => onCallback(phone)}>Call Back</button>
      <button type="button" onClick={() => onMarkHandled(!handled)}>
        {handled ? "Mark Unhandled" : "Mark Handled"}
      </button>
    </div>
  ),
  CallTranscript: ({
    messages,
  }: {
    messages: Array<{ speaker: string; text: string; timestamp: string }>;
  }) => (
    <div data-testid="transcript">
      {messages.map((m, i) => (
        <div key={i} data-testid={`msg-${m.speaker}`}>{m.text}</div>
      ))}
    </div>
  ),
  AudioPlayer: ({ src, duration }: { src: string; duration: string }) => (
    <div data-testid="audio-player">
      <span>{src}</span>
      <span>{duration}</span>
    </div>
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

import { CallDetailPage } from "@/pages/CallDetailPage";


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage(callId = "call-123") {
  const qc = makeQC();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/calls/${callId}`]}>
        <Routes>
          <Route path="/calls" element={<div>CallHistory</div>} />
          <Route path="/calls/:id" element={<CallDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// sampleCall has no transcript so CallTranscript is not rendered in core tests.
// Tests that need transcript coverage use sampleCallWithTranscript.
const sampleCall = {
  id: "call-123",
  callerName: "Jane Doe",
  callerPhone: "+61400000001",
  intent: "quote",
  summary: "Needs a quote for solar panel installation",
  timestamp: "Today 9:00 AM",
  duration: "3m 22s",
  needsCallback: true,
  urgent: false,
};

const sampleCallWithTranscript = {
  ...sampleCall,
  transcript: "Caller: Hi, I need a quote for solar panels.",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CallDetailPage", () => {
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

  it("renders call details on success", async () => {
    mockApiFetch.mockResolvedValue(sampleCall);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    });

    expect(screen.getByText("Needs a quote for solar panel installation")).toBeInTheDocument();
    expect(screen.getByText("Today 9:00 AM")).toBeInTheDocument();
    expect(screen.getByText("3m 22s")).toBeInTheDocument();
  });

  it("shows needs-callback badge when needsCallback is true", async () => {
    mockApiFetch.mockResolvedValue(sampleCall);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    });

    // Badge or indicator for needs callback
    expect(
      screen.getByText(/needs callback/i) ||
      screen.getByText(/callback/i)
    ).toBeInTheDocument();
  });

  it("shows PageError on fetch failure with retry", async () => {
    mockApiFetch.mockRejectedValue(new Error("Network error"));

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    });
  });

  it("back button navigates to /calls", async () => {
    mockApiFetch.mockResolvedValue(sampleCall);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("link", { name: /back/i }));

    await waitFor(() => {
      expect(screen.getByText("CallHistory")).toBeInTheDocument();
    });
  });

  it("fetches using the call id from the URL", async () => {
    mockApiFetch.mockResolvedValue(sampleCall);

    renderPage("call-456");

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("call-456")
      );
    });
  });
});
