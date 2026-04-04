/**
 * CallDetailPage — full detail view for a single call (story-5-6).
 * Updated dashboard-15: uses @chokaau/ui CallDetailActionBar, CallTranscript,
 * AudioPlayer.
 *
 * Fetches GET /api/calls/:id via TanStack Query.
 * Shows: caller name/phone, intent badge, summary, transcript, timestamp,
 * duration, needs-callback indicator, back navigation.
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { apiFetch } from "@/lib/api-client";
import {
  PageError,
  Skeleton,
  CallDetailActionBar,
  CallTranscript,
  AudioPlayer,
} from "@chokaau/ui";

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
  recordingUrl?: string;
  timestamp: string;
  duration: string;
  needsCallback: boolean;
  handled?: boolean;
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

interface TranscriptMessage {
  speaker: "ai" | "caller";
  text: string;
  timestamp: string;
}

/**
 * Parse a plain-text transcript into structured TranscriptMessage[].
 * Expected format: lines prefixed "AI: " or "Caller: " with optional timestamps.
 * Falls back to a single caller message when format is unknown.
 */
function parseTranscript(raw: string): TranscriptMessage[] {
  const lines = raw.split("\n").filter((l) => l.trim());
  const messages: TranscriptMessage[] = [];
  let lineIndex = 0;

  for (const line of lines) {
    const aiMatch = /^(?:AI|Receptionist|Choka):\s*(.+)/i.exec(line);
    const callerMatch = /^(?:Caller|Customer|Client):\s*(.+)/i.exec(line);
    lineIndex++;

    if (aiMatch) {
      messages.push({
        speaker: "ai",
        text: aiMatch[1],
        timestamp: String(lineIndex),
      });
    } else if (callerMatch) {
      messages.push({
        speaker: "caller",
        text: callerMatch[1],
        timestamp: String(lineIndex),
      });
    } else if (line.trim()) {
      // Unrecognised line — treat as caller speech
      messages.push({
        speaker: "caller",
        text: line.trim(),
        timestamp: String(lineIndex),
      });
    }
  }

  return messages.length > 0
    ? messages
    : [{ speaker: "caller", text: raw.trim(), timestamp: "0" }];
}

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
  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery<CallDetail>({
    queryKey: ["calls", id],
    queryFn: () => apiFetch<CallDetail>(`/api/calls/${id}`),
    enabled: Boolean(id),
  });

  const markHandledMutation = useMutation({
    mutationFn: (handled: boolean) =>
      apiFetch(`/api/calls/${id}/handled`, {
        method: "PUT",
        body: JSON.stringify({ handled }),
      }),
    onSuccess: (_result, handled) => {
      queryClient.setQueryData(["calls", id], (prev: CallDetail | undefined) =>
        prev ? { ...prev, handled } : prev
      );
    },
  });

  if (isLoading) {
    return (
      <div className="min-h-full">
        <div className="border-b border-border p-4">
          <Skeleton className="h-5 w-20" />
        </div>
        <CallDetailSkeleton />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="min-h-full p-6">
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

  const transcriptMessages = data.transcript
    ? parseTranscript(data.transcript)
    : [];

  return (
    <div className="min-h-full pb-24">
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
              <p className="mt-1 text-sm text-muted-foreground">
                {data.callerPhone}
              </p>
            </div>
          </div>

          {/* Intent + meta */}
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${INTENT_COLOURS[data.intent]}`}
            >
              {INTENT_LABEL[data.intent]}
            </span>
            <span>{data.duration}</span>
            <span>{data.timestamp}</span>
            {data.needsCallback && (
              <span className="rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-800">
                Needs callback
              </span>
            )}
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

        {/* Audio recording */}
        {data.recordingUrl && (
          <section>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Recording
            </h2>
            <AudioPlayer
              src={data.recordingUrl}
              duration={data.duration}
            />
          </section>
        )}

        {/* Transcript */}
        {transcriptMessages.length > 0 && (
          <section>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Transcript
            </h2>
            <CallTranscript messages={transcriptMessages} />
          </section>
        )}
      </div>

      {/* Sticky action bar */}
      <CallDetailActionBar
        phone={data.callerPhone}
        handled={data.handled ?? false}
        onCallback={(phone) => {
          window.location.href = `tel:${phone}`;
        }}
        onMarkHandled={(handled) => {
          markHandledMutation.mutate(handled);
        }}
      />
    </div>
  );
}

export default CallDetailPage;
