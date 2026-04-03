/**
 * useLogout — cache-clearing sign-out (Epic 5 remaining / story-4-2 gap).
 *
 * Wraps signOut with:
 *   1. queryClient.clear()   — removes all TanStack Query cache
 *   2. sessionStorage.clear() — removes any session-scoped data
 *   3. Zustand reset         — resets call history filter state
 *
 * Usage: const logout = useLogout(); await logout();
 */
import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useCognitoAuth } from "@/adapters/cognito-auth-provider";
import { useCallHistoryFilters } from "@/stores/call-history-filters";

export function useLogout(): () => Promise<void> {
  const { signOut } = useCognitoAuth();
  const queryClient = useQueryClient();
  const resetFilters = useCallHistoryFilters((s) => s.setStatus);

  return useCallback(async () => {
    // 1. Clear TanStack Query cache — no stale data after re-login
    queryClient.clear();

    // 2. Clear session storage — removes any ephemeral UI state
    sessionStorage.clear();

    // 3. Reset Zustand filter store to defaults
    resetFilters("all");

    // 4. Cognito signOut (also clears Amplify session)
    await signOut();
  }, [signOut, queryClient, resetFilters]);
}
