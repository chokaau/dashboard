/**
 * Tests for query-client.ts — covers getRetryDelay and queryClient export.
 */
import { describe, it, expect } from "vitest";
import { queryClient } from "@/lib/query-client";

describe("queryClient", () => {
  it("exports a QueryClient instance", () => {
    expect(queryClient).toBeDefined();
    expect(typeof queryClient.invalidateQueries).toBe("function");
  });

  it("default query options have staleTime=30000", () => {
    const defaults = queryClient.getDefaultOptions().queries;
    expect(defaults?.staleTime).toBe(30_000);
  });

  it("default query options have retry=3", () => {
    const defaults = queryClient.getDefaultOptions().queries;
    expect(defaults?.retry).toBe(3);
  });

  it("retryDelay returns exponential backoff capped at 8000", () => {
    const retryDelay = queryClient.getDefaultOptions().queries
      ?.retryDelay as (attempt: number) => number;
    expect(retryDelay(0)).toBe(1000);
    expect(retryDelay(1)).toBe(2000);
    expect(retryDelay(2)).toBe(4000);
    expect(retryDelay(3)).toBe(8000); // 8s cap: min(8000,8000)=8000
    expect(retryDelay(10)).toBe(8000); // still capped
  });
});
