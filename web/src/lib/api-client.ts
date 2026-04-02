/**
 * apiFetch — authenticated API client (story-5-2).
 *
 * - Attaches Authorization: Bearer {idToken} to every request
 * - 15-second AbortSignal.timeout
 * - Throws ApiError on non-2xx responses
 * - On 401: calls signOut() exactly once across concurrent requests
 */
import { getAuthContext } from "@/adapters/cognito-auth-provider";

// ---------------------------------------------------------------------------
// ApiError
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// 401 deduplication flag (module-level, reset on next successful request)
// ---------------------------------------------------------------------------

let isSigningOut = false;

// ---------------------------------------------------------------------------
// apiFetch
// ---------------------------------------------------------------------------

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const TIMEOUT_MS = 15_000;

export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const auth = getAuthContext();
  const token = await auth?.getAccessToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (err) {
    // AbortSignal.timeout fires a TimeoutError (subclass of DOMException)
    if (
      err instanceof DOMException &&
      (err.name === "TimeoutError" || err.name === "AbortError")
    ) {
      throw new ApiError(408, "Request timed out", "REQUEST_TIMEOUT");
    }
    throw err;
  }

  if (response.ok) {
    isSigningOut = false;
    return response.json() as Promise<T>;
  }

  // Parse error body for structured message/code
  let message = response.statusText || "Request failed";
  let code: string | undefined;
  try {
    const body = (await response.json()) as { message?: string; code?: string };
    if (body.message) message = body.message;
    if (body.code) code = body.code;
  } catch {
    // ignore parse errors
  }

  if (response.status === 401) {
    if (!isSigningOut) {
      isSigningOut = true;
      const ctx = getAuthContext();
      if (ctx) {
        void ctx.signOut();
      }
    }
  }

  throw new ApiError(response.status, message, code);
}
