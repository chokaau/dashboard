/**
 * CallHistoryPage — paginated, filterable call history (story-5-5).
 *
 * Filter state lives in Zustand (useCallHistoryFilters).
 * Data is fetched via TanStack Query; query key includes all filter params
 * so changing any filter invalidates the cache and triggers a new fetch.
 */
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { PhoneOff } from "lucide-react";
import { apiFetch } from "@/lib/api-client";
import { useCallHistoryFilters } from "@/stores/call-history-filters";
import type { CallHistoryStatus, CallHistoryDateRange } from "@/stores/call-history-filters";
import { CallCard, CallHistoryFilterBar, EmptyState, Skeleton } from "@chokaau/ui";
import type { CallCardProps, CallHistoryTab, DateFilter, LeadIntent } from "@chokaau/ui";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CallItem {
  id: string;
  callerName: string;
  callerPhone: string;
  intent: LeadIntent;
  summary: string;
  timestamp: string;
  duration: string;
  needsCallback: boolean;
  urgent?: boolean;
}

interface CallsStats {
  totalToday: number;
  needsCallback: number;
  total: number;
}

interface CallsResponse {
  calls: CallItem[];
  stats: CallsStats;
  pagination: { page: number; pageSize: number; total: number };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toCallCardStatus(call: CallItem): CallCardProps["status"] {
  if (call.needsCallback) return "missed";
  return "completed";
}

/** Map store status → CallHistoryTab (filter bar uses its own union type) */
function toFilterBarTab(status: CallHistoryStatus): CallHistoryTab {
  // "needs-callback" maps directly; others map 1:1
  return status as CallHistoryTab;
}

/** Map store dateRange → DateFilter */
function toDateFilter(dateRange: CallHistoryDateRange): DateFilter {
  return dateRange as DateFilter;
}

/** Build query string from filter params */
function buildQueryString(params: {
  status: CallHistoryStatus;
  dateRange: CallHistoryDateRange;
  page: number;
}): string {
  const parts: string[] = [];
  if (params.status !== "all") parts.push(`status=${params.status}`);
  if (params.dateRange !== "all") parts.push(`dateRange=${params.dateRange}`);
  parts.push(`page=${params.page}`);
  return parts.length > 0 ? `?${parts.join("&")}` : "";
}

// ---------------------------------------------------------------------------
// Skeleton loader
// ---------------------------------------------------------------------------

function CallHistorySkeleton() {
  return (
    <div className="space-y-3 p-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-20 w-full rounded-lg" />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CallHistoryPage() {
  const navigate = useNavigate();
  const { status, dateRange, page, setStatus, setDateRange, setPage } =
    useCallHistoryFilters();

  const { data, isLoading } = useQuery<CallsResponse>({
    queryKey: ["calls", { status, dateRange, page }],
    queryFn: () => {
      const qs = buildQueryString({ status, dateRange, page });
      return apiFetch<CallsResponse>(`/api/calls${qs}`);
    },
  });

  // ------------------------------------------------------------------
  // Handlers — map filter bar types back to store types
  // ------------------------------------------------------------------
  const handleTabChange = (tab: CallHistoryTab) => {
    setStatus(tab as CallHistoryStatus);
  };

  const handleDateFilterChange = (filter: DateFilter) => {
    setDateRange(filter as CallHistoryDateRange);
  };

  const handleSearchChange = (_query: string) => {
    // Search is UI-only for now; reset to page 1 on any change
    setPage(1);
  };

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <div className="flex min-h-screen flex-col">
      {/* Sticky filter bar */}
      <CallHistoryFilterBar
        activeTab={toFilterBarTab(status)}
        onTabChange={handleTabChange}
        dateFilter={toDateFilter(dateRange)}
        onDateFilterChange={handleDateFilterChange}
        searchQuery=""
        onSearchChange={handleSearchChange}
        needsCallbackCount={data?.stats.needsCallback}
      />

      {/* Content */}
      <div className="flex-1">
        {isLoading ? (
          <CallHistorySkeleton />
        ) : data && data.calls.length > 0 ? (
          <div className="space-y-2 p-4">
            {data.calls.map((call) => (
              <CallCard
                key={call.id}
                callerName={call.callerName}
                callerPhone={call.callerPhone}
                intent={call.intent}
                summary={call.summary}
                timestamp={call.timestamp}
                duration={call.duration}
                needsCallback={call.needsCallback}
                status={toCallCardStatus(call)}
                onClick={() => navigate(`/calls/${call.id}`)}
              />
            ))}

            {/* Pagination */}
            {data.pagination.total > data.pagination.pageSize && (
              <div className="flex items-center justify-center gap-3 pt-4">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                  className="rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="text-sm text-muted-foreground">
                  Page {page} of{" "}
                  {Math.ceil(data.pagination.total / data.pagination.pageSize)}
                </span>
                <button
                  type="button"
                  disabled={
                    page >= Math.ceil(data.pagination.total / data.pagination.pageSize)
                  }
                  onClick={() => setPage(page + 1)}
                  className="rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        ) : (
          <div aria-live="polite" className="p-4">
            <EmptyState
              icon={<PhoneOff className="h-8 w-8" />}
              title="No calls found"
              description="No calls match the current filters. Try adjusting your search or date range."
            />
          </div>
        )}
      </div>
    </div>
  );
}

export default CallHistoryPage;
