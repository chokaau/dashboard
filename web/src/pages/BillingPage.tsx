/**
 * BillingPage — trial status, upgrade CTA, subscription info (story-5-8).
 *
 * Fetches GET /api/billing.
 * States: trial-active, trial-expiring (≤3 days), trial-expired, active subscription.
 */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle } from "lucide-react";
import { apiFetch } from "@/lib/api-client";
import { Skeleton } from "@choka/ui/src/components/primitives/Skeleton";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type BillingStatus = "trial" | "active" | "expired" | "cancelled";

interface BillingData {
  status: BillingStatus;
  trialDaysRemaining: number;
  planName: string;
  planPrice: number;
  nextBillingDate?: string;
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function BillingSkeleton() {
  return (
    <div className="space-y-4 p-6">
      <Skeleton className="h-6 w-24" />
      <Skeleton className="h-28 w-full rounded-lg" />
      <Skeleton className="h-6 w-40" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-10 w-56 rounded-md" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TrialBanner({ daysRemaining }: { daysRemaining: number }) {
  const isExpiring = daysRemaining <= 3;
  const isExpired = daysRemaining <= 0;

  if (isExpired) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
        <div>
          <p className="font-semibold text-red-900">Trial expired</p>
          <p className="mt-0.5 text-sm text-red-700">
            Your trial has ended. Upgrade now to keep your AI answering calls.
          </p>
        </div>
      </div>
    );
  }

  if (isExpiring) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
        <div>
          <p className="font-semibold text-amber-900">
            Trial ending in {daysRemaining} days
          </p>
          <p className="mt-0.5 text-sm text-amber-700">
            Upgrade now to keep your AI answering calls.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4">
      <p className="font-semibold text-foreground">Free Trial</p>
      <p className="mt-0.5 text-sm text-muted-foreground">
        {daysRemaining} days remaining &mdash; No credit card required
      </p>
    </div>
  );
}

function ActiveSubscriptionBanner({
  planName,
  planPrice,
  nextBillingDate,
}: {
  planName: string;
  planPrice: number;
  nextBillingDate?: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-green-200 bg-green-50 p-4">
      <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-green-600" />
      <div>
        <p className="font-semibold text-green-900">
          Active &mdash; {planName} Plan
        </p>
        <p className="mt-0.5 text-sm text-green-700">
          ${planPrice}/month
          {nextBillingDate && ` \u00b7 Next billing: ${nextBillingDate}`}
        </p>
      </div>
    </div>
  );
}

const PLAN_FEATURES = [
  "Unlimited calls answered",
  "Call transcripts + summaries",
  "SMS lead notifications",
  "Cancel anytime",
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BillingPage() {
  const { data, isLoading } = useQuery<BillingData>({
    queryKey: ["billing"],
    queryFn: () => apiFetch<BillingData>("/api/billing"),
  });

  if (isLoading) {
    return <BillingSkeleton />;
  }

  const isTrial = data?.status === "trial";
  const isActive = data?.status === "active";
  const showUpgradeCTA = isTrial || data?.status === "expired";

  return (
    <div className="mx-auto max-w-xl p-6">
      <h1 className="mb-6 text-xl font-semibold text-foreground">Billing</h1>

      {/* Status banner */}
      {isTrial && (
        <TrialBanner daysRemaining={data?.trialDaysRemaining ?? 0} />
      )}
      {isActive && (
        <ActiveSubscriptionBanner
          planName={data?.planName ?? "Starter"}
          planPrice={data?.planPrice ?? 249}
          nextBillingDate={data?.nextBillingDate}
        />
      )}

      {/* Plan details */}
      <div className="mt-6">
        <h2 className="text-base font-semibold text-foreground">
          {data?.planName ?? "Starter"} Plan &mdash; ${data?.planPrice ?? 249}/month
        </h2>
        <ul className="mt-3 space-y-1.5">
          {PLAN_FEATURES.map((f) => (
            <li key={f} className="flex items-center gap-2 text-sm text-muted-foreground">
              <CheckCircle className="h-4 w-4 shrink-0 text-green-500" />
              {f}
            </li>
          ))}
        </ul>
      </div>

      {/* Upgrade CTA */}
      {showUpgradeCTA && (
        <button
          type="button"
          className="mt-6 w-full rounded-md bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
        >
          {data?.status === "expired"
            ? "Upgrade now \u2014 $249/month"
            : `Start subscription \u2014 $${data?.planPrice ?? 249}/month`}
        </button>
      )}

      {/* Help */}
      <p className="mt-4 text-center text-sm text-muted-foreground">
        Questions?{" "}
        <a
          href="mailto:support@choka.com.au"
          className="text-primary underline-offset-2 hover:underline"
        >
          Chat with us
        </a>
      </p>
    </div>
  );
}

export default BillingPage;
