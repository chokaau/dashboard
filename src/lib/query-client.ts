/**
 * Shared TanStack Query client (story-5-2).
 *
 * staleTime: 30s, retry: 3 with exponential backoff capped at 8s,
 * refetchOnWindowFocus: true.
 */
import { QueryClient } from "@tanstack/react-query";

function getRetryDelay(attemptIndex: number): number {
  // Exponential backoff: 1s, 2s, 4s — capped at 8s
  return Math.min(1000 * 2 ** attemptIndex, 8000);
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 3,
      retryDelay: getRetryDelay,
      refetchOnWindowFocus: true,
    },
  },
});
