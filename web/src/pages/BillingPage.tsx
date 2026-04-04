/**
 * BillingPage — trial status, upgrade CTA, subscription info (story-5-8).
 * Updated dashboard-15: uses @chokaau/ui TrialBanner, CurrentPlanCard.
 *
 * Fetches GET /api/billing.
 * States: trial-active, trial-expiring (≤3 days), trial-expired, active subscription.
 */
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import { Skeleton, TrialBanner, CurrentPlanCard } from "@chokaau/ui";

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
      <Skeleton className="h-10 w-56 rounded-md" />
    </div>
  );
}

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

  const status = data?.status ?? "trial";
  const daysRemaining = data?.trialDaysRemaining ?? 0;
  const planName = data?.planName ?? "Starter";
  const planPrice = data?.planPrice ?? 249;
  const nextBillingDate = data?.nextBillingDate;

  const currentPlanStatus: "trial" | "active" | "expired" =
    status === "active" ? "active" : status === "expired" ? "expired" : "trial";

  return (
    <div className="mx-auto max-w-xl p-6">
      <h1 className="mb-6 text-xl font-semibold text-foreground">Billing</h1>

      {/* Trial banner — shown when trial is active */}
      {status === "trial" && (
        <TrialBanner
          daysRemaining={daysRemaining}
          onUpgrade={() => {
            // Stripe/billing portal integration — Phase 2
          }}
        />
      )}

      {/* Current plan card */}
      <div className="mt-6">
        <CurrentPlanCard
          status={currentPlanStatus}
          planName={planName}
          daysRemaining={daysRemaining}
          nextBillingDate={nextBillingDate}
          amount={`$${planPrice}/month`}
          onUpgrade={() => {
            // Stripe/billing portal integration — Phase 2
          }}
        />
      </div>

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
