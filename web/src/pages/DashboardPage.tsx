/**
 * DashboardPage — stat cards, needs-callback panel, recent calls (story-5-4).
 * Updated dashboard-10: shows ActivationBanner when activation_status is "pending".
 *
 * Real-time updates via SSE (useCallEvents). No polling — SSE drives
 * queryClient invalidation. Falls back to 30s polling if SSE is unavailable.
 * Full loading / error / success states.
 */
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useCallEvents } from "@/hooks/use-call-events";
import { Phone, PhoneCall, PhoneOff, Clock } from "lucide-react";
import { apiFetch } from "@/lib/api-client";
import { ActivationBanner, CallCard, DashboardStatCard, NeedsCallbackPanel, PageError } from "@chokaau/ui";
import type { CallCardProps, CallbackLead, LeadIntent } from "@chokaau/ui";

// ---------------------------------------------------------------------------
// Types (mirrors BFF response)
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

interface BillingResponse {
  plan: string;
  trialDaysRemaining: number;
  trialEndDate: string;
  isTrialExpired: boolean;
  activationStatus: "none" | "pending" | "active";
  product: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toCallCardStatus(call: CallItem): CallCardProps["status"] {
  if (call.needsCallback) return "missed";
  return "completed";
}

function toCallbackLead(call: CallItem): CallbackLead {
  return {
    callerName: call.callerName,
    callerPhone: call.callerPhone,
    intent: call.intent,
    summary: call.summary,
    timestamp: call.timestamp,
    urgent: call.urgent,
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DashboardPage() {
  const navigate = useNavigate();

  // Open SSE connection — invalidates ['calls'] on call_completed events.
  // Falls back to 30s polling if SSE is unavailable.
  useCallEvents();

  const { data, isLoading, isError, refetch } = useQuery<CallsResponse>({
    queryKey: ["calls"],
    queryFn: () => apiFetch<CallsResponse>("/api/calls"),
    // No refetchInterval here — SSE drives invalidation.
    // Polling fallback (30s) is set by useCallEvents on SSE failure.
  });

  const { data: billingData } = useQuery<BillingResponse>({
    queryKey: ["billing"],
    queryFn: () => apiFetch<BillingResponse>("/api/billing"),
    // Background fetch — does not block dashboard render
    staleTime: 60_000,
  });

  // ------------------------------------------------------------------
  // Loading state
  // ------------------------------------------------------------------
  if (isLoading) {
    return (
      <div className="space-y-6 p-6">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <DashboardStatCard label="Calls today" isLoading />
          <DashboardStatCard label="Need callback" isLoading />
          <DashboardStatCard label="Total calls" isLoading />
          <DashboardStatCard label="Avg duration" isLoading />
        </div>
        <NeedsCallbackPanel leads={[]} onCallback={() => {}} />
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Error state
  // ------------------------------------------------------------------
  if (isError || !data) {
    return (
      <div className="p-6">
        <PageError
          title="Failed to load dashboard"
          description="Could not load call data. Please try again."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Success state
  // ------------------------------------------------------------------
  const { calls, stats } = data;
  const callbackLeads = calls
    .filter((c) => c.needsCallback)
    .map(toCallbackLead);
  const recentCalls = calls.slice(0, 10);

  return (
    <div className="space-y-6 p-6">
      {/* Activation banner — shown when pending activation */}
      <ActivationBanner status={billingData?.activationStatus ?? "none"} />

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <DashboardStatCard
          label="Calls today"
          value={String(stats.totalToday)}
          icon={<Phone className="h-4 w-4" />}
        />
        <DashboardStatCard
          label="Need callback"
          value={String(stats.needsCallback)}
          icon={<PhoneOff className="h-4 w-4" />}
        />
        <DashboardStatCard
          label="Total calls"
          value={String(stats.total)}
          icon={<PhoneCall className="h-4 w-4" />}
        />
        <DashboardStatCard
          label="Avg duration"
          value="—"
          icon={<Clock className="h-4 w-4" />}
        />
      </div>

      {/* Needs callback panel */}
      <NeedsCallbackPanel
        leads={callbackLeads}
        onCallback={(phone) => {
          if (navigator.clipboard) {
            void navigator.clipboard.writeText(phone);
          }
        }}
      />

      {/* Recent calls */}
      {recentCalls.length > 0 && (
        <section aria-label="Recent calls">
          <h2 className="mb-3 text-base font-semibold text-foreground">
            Recent calls
          </h2>
          <div className="space-y-2">
            {recentCalls.map((call) => (
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
                onCallback={(phone) => {
                  if (navigator.clipboard) {
                    void navigator.clipboard.writeText(phone);
                  }
                }}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default DashboardPage;
