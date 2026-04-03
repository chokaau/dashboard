/**
 * ActivationBanner — shown on /dashboard when activation_status is "pending" (dashboard-10).
 *
 * Dismissed for the session via local state (no persistence needed).
 */
import { useState } from "react";
import { X } from "lucide-react";

type ActivationStatus = "none" | "pending" | "active";

interface ActivationBannerProps {
  activationStatus: ActivationStatus;
}

export function ActivationBanner({ activationStatus }: ActivationBannerProps) {
  const [dismissed, setDismissed] = useState(false);

  if (activationStatus !== "pending" || dismissed) {
    return null;
  }

  return (
    <div
      role="alert"
      className="flex items-start justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800"
    >
      <p>
        Your Voice service is being reviewed. We&apos;ll activate it within 24 hours.
      </p>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => setDismissed(true)}
        className="shrink-0 rounded p-0.5 hover:bg-amber-100"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export default ActivationBanner;
