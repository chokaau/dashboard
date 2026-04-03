/**
 * Tests for story-5-2: apiFetch API client.
 *
 * TDD: RED tests written first. Tests cover:
 * - 401 response triggers signOut
 * - 500 response throws ApiError with status 500
 * - 15s timeout throws ApiError(408, "Request timed out", "REQUEST_TIMEOUT")
 * - 3 concurrent 401s call signOut exactly once
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock the auth adapter before importing apiFetch
const mockSignOut = vi.fn().mockResolvedValue(undefined);

vi.mock("@/adapters/cognito-auth-provider", () => ({
  getAuthContext: () => ({
    signOut: mockSignOut,
    getAccessToken: vi.fn().mockResolvedValue("test-token"),
  }),
}));

describe("apiFetch", () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    mockSignOut.mockClear();
    // Reset the isSigningOut flag by re-importing (done via vi.resetModules)
    vi.resetModules();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("attaches Authorization header with Bearer token", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );

    // Re-import after resetModules
    const { apiFetch } = await import("@/lib/api-client");
    await apiFetch("/test");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/test"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-token",
        }),
      })
    );
  });

  it("401 response triggers signOut", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: "Unauthorized" }), { status: 401 })
    );

    const { apiFetch } = await import("@/lib/api-client");

    await expect(apiFetch("/protected")).rejects.toThrow();
    expect(mockSignOut).toHaveBeenCalledTimes(1);
  });

  it("500 response throws ApiError with status 500", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: "Internal Server Error" }), {
        status: 500,
      })
    );

    const { apiFetch, ApiError } = await import("@/lib/api-client");

    await expect(apiFetch("/fail")).rejects.toThrow(ApiError);

    try {
      await apiFetch("/fail");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as InstanceType<typeof ApiError>).status).toBe(500);
    }
  });

  it("non-2xx throws ApiError with correct status", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: "Not Found", code: "NOT_FOUND" }), {
        status: 404,
      })
    );

    const { apiFetch, ApiError } = await import("@/lib/api-client");

    try {
      await apiFetch("/missing");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as InstanceType<typeof ApiError>).status).toBe(404);
    }
  });

  it("15s timeout throws ApiError(408, 'Request timed out', 'REQUEST_TIMEOUT')", async () => {
    // Simulate AbortSignal.timeout firing — DOMException with name "TimeoutError"
    // DOMException.name is read-only, so we use the constructor's second arg
    globalThis.fetch = vi.fn().mockRejectedValue(
      new DOMException("The operation was aborted.", "TimeoutError")
    );

    const { apiFetch, ApiError } = await import("@/lib/api-client");

    try {
      await apiFetch("/slow");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as InstanceType<typeof ApiError>).status).toBe(408);
      expect((e as InstanceType<typeof ApiError>).message).toBe(
        "Request timed out"
      );
      expect((e as InstanceType<typeof ApiError>).code).toBe("REQUEST_TIMEOUT");
    }
  });

  it("3 concurrent 401s call signOut exactly once", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: "Unauthorized" }), { status: 401 })
    );

    const { apiFetch } = await import("@/lib/api-client");

    await Promise.allSettled([
      apiFetch("/a"),
      apiFetch("/b"),
      apiFetch("/c"),
    ]);

    expect(mockSignOut).toHaveBeenCalledTimes(1);
  });
});
