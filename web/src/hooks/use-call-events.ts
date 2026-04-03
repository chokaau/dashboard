/**
 * useCallEvents — SSE client for real-time call updates (story-4-2 / Epic 7).
 *
 * Connects to GET /api/events?token=<idToken> when authenticated.
 * On call_completed event: invalidates the ['calls'] TanStack Query.
 * On ping: no-op.
 * On error: exponential backoff reconnect (1s → 2s → 4s, capped at 30s).
 * On 5 consecutive errors with no success: falls back to 30s polling.
 * On signOut: closes connection, cancels reconnect.
 *
 * Auth note: EventSource cannot set the Authorization header.
 * The BFF accepts ?token= on /api/events only (SSE-specific path).
 * Token is fetched fresh on every (re)connect attempt.
 */
import { useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useCognitoAuth } from "@/adapters/cognito-auth-provider";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const MAX_BACKOFF_MS = 30_000;
const FALLBACK_THRESHOLD = 5;

export function useCallEvents(): void {
  const { isAuthenticated, getAccessToken, signOut } = useCognitoAuth();
  const queryClient = useQueryClient();

  // Track consecutive errors (never received a successful ping/event)
  const errorCountRef = useRef(0);
  const successRef = useRef(false);
  const esRef = useRef<EventSource | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef = useRef(false);

  const clearReconnectTimer = useCallback(() => {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const close = useCallback(() => {
    clearReconnectTimer();
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, [clearReconnectTimer]);

  const connect = useCallback(async () => {
    if (unmountedRef.current) return;

    let token: string;
    try {
      token = await getAccessToken();
    } catch {
      // Cognito session expired — sign out, stop reconnecting
      void signOut();
      return;
    }

    const url = `${API_BASE}/api/events?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url, { withCredentials: false });
    esRef.current = es;

    es.addEventListener("ping", () => {
      // Heartbeat — mark success, reset error count
      successRef.current = true;
      errorCountRef.current = 0;
      // Remove polling fallback if it was enabled
      queryClient.setQueryDefaults(["calls"], { refetchInterval: undefined });
    });

    es.addEventListener("call_completed", () => {
      successRef.current = true;
      errorCountRef.current = 0;
      void queryClient.invalidateQueries({ queryKey: ["calls"] });
    });

    es.addEventListener("reconnect", () => {
      // Server-initiated reconnect after timeout
      close();
      if (!unmountedRef.current) {
        void connect();
      }
    });

    es.onerror = () => {
      if (unmountedRef.current) return;
      close();

      errorCountRef.current += 1;

      // Fallback to polling after FALLBACK_THRESHOLD consecutive errors
      // with no intervening success
      if (!successRef.current && errorCountRef.current >= FALLBACK_THRESHOLD) {
        console.warn(
          "[useCallEvents] SSE failed after",
          errorCountRef.current,
          "attempts — falling back to 30s polling"
        );
        queryClient.setQueryDefaults(["calls"], { refetchInterval: 30_000 });
      }

      // Exponential backoff: 1s, 2s, 4s, 8s, 16s, capped at 30s
      const backoffMs = Math.min(
        1000 * 2 ** (errorCountRef.current - 1),
        MAX_BACKOFF_MS
      );

      timeoutRef.current = setTimeout(() => {
        if (!unmountedRef.current) {
          void connect();
        }
      }, backoffMs);
    };
  }, [getAccessToken, signOut, queryClient, close]);

  useEffect(() => {
    unmountedRef.current = false;
    if (!isAuthenticated) return;

    void connect();

    return () => {
      unmountedRef.current = true;
      close();
    };
  }, [isAuthenticated, connect, close]);
}
