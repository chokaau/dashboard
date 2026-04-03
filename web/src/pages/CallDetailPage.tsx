/**
 * CallDetailPage — full detail view for a single call (story-5-6).
 *
 * Fetches GET /api/calls/:id via TanStack Query.
 * Shows: caller name/phone, intent badge, summary, transcript, timestamp,
 * duration, needs-callback indicator, back navigation.
 */
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Clock, Phone, PhoneOff } from "lucide-react";
import { apiFetch } from "@/lib/api-client";
import { PageError, Skeleton } from "@chokaau/ui";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LeadIntent = "quote" | "info" | "urgent" | "complaint" | "other";

interface CallDetail {
  id: string;
  callerName: string;
  callerPhone: string;
  intent: LeadIntent;
  summary: string;
  transcript?: string;
  timestamp: string;
  duration: string;
  needsCallback: boolean;
  urgent?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const INTENT_LABEL: Record<LeadIntent, string> = {
  quote: "Quote Request",
  info: "Information",
  urgent: "Urgent",
  complaint: "Complaint",
  other: "Other",
};

const INTENT_COLOURS: Record<LeadIntent, string> = {
  quote: "bg-blue-100 text-blue-800",
  info: "bg-gray-100 text-gray-800",
  urgent: "bg-red-100 text-red-800",
  complaint: "bg-orange-100 text-orange-800",
  other: "bg-gray-100 text-gray-700",
};

// ---------------------------------------------------------------------------
// Skeleton loader
// ---------------------------------------------------------------------------

function CallDetailSkeleton() {
  return (
    <div className="space-y-4 p-6">
      <Skeleton className="h-6 w-32" />
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-24 w-full rounded-lg" />
      <Skeleton className="h-40 w-full rounded-lg" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CallDetailPage() {
  const { id } = useParams<{ id: string }>();

  const { data, isLoading, isError, refetch } = useQuery<CallDetail>({
    queryKey: ["calls", id],
    queryFn: () => apiFetch<CallDetail>(`/api/calls/${id}`),
    enabled: Boolean(id),
  });

  if (isLoading) {
    return (
      <div className="min-h-screen">
        <div className="border-b border-border p-4">
          <Skeleton className="h-5 w-20" />
        </div>
        <CallDetailSkeleton />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="min-h-screen p-6">
        <Link
          to="/calls"
          aria-label="Back to call history"
          className="mb-6 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Link>
        <PageError
          title="Failed to load call"
          description="Could not load call details. Please try again."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Header / back nav */}
      <div className="sticky top-0 z-10 border-b border-border bg-background px-4 py-3">
        <Link
          to="/calls"
          aria-label="Back to call history"
          className="flex w-fit items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Link>
      </div>

      {/* Content */}
      <div className="space-y-6 p-6">
        {/* Caller info */}
        <section>
          <div className="flex items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold text-foreground">
                {data.callerName}
              </h1>
              <div className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
                <Phone className="h-3.5 w-3.5" />
                {data.callerPhone}
              </div>
            </div>

            {/* Needs callback badge */}
            {data.needsCallback && (
              <span className="flex items-center gap-1 rounded-full bg-yellow-100 px-2.5 py-1 text-xs font-medium text-yellow-800">
                <PhoneOff className="h-3 w-3" />
                Needs callback
              </span>
            )}
          </div>

          {/* Intent + meta */}
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${INTENT_COLOURS[data.intent]}`}
            >
              {INTENT_LABEL[data.intent]}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {data.duration}
            </span>
            <span>{data.timestamp}</span>
          </div>
        </section>

        {/* AI summary */}
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Summary
          </h2>
          <p className="rounded-lg border border-border bg-muted/30 p-4 text-sm leading-relaxed text-foreground">
            {data.summary}
          </p>
        </section>

        {/* Transcript */}
        {data.transcript && (
          <section>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Transcript
            </h2>
            <pre className="whitespace-pre-wrap rounded-lg border border-border bg-muted/30 p-4 font-mono text-xs leading-relaxed text-foreground">
              {data.transcript}
            </pre>
          </section>
        )}
      </div>
    </div>
  );
}

export default CallDetailPage;
