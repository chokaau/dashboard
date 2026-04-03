/**
 * SetupPage — product selection (dashboard-10).
 *
 * Replaces the call-forwarding wizard as the /setup entry point.
 * Shows available products: Voice (active) and Quote (coming soon).
 * "Set up Voice" navigates to /setup/voice.
 */
import { useNavigate } from "react-router-dom";
import { Mic, FileText } from "lucide-react";

export function SetupPage() {
  const navigate = useNavigate();

  return (
    <div className="mx-auto max-w-md p-6">
      <h1 className="mb-2 text-xl font-semibold text-foreground">Choose a product</h1>
      <p className="mb-8 text-sm text-muted-foreground">
        Select the product you&apos;d like to set up for your business.
      </p>

      <div className="space-y-4">
        {/* Voice product card */}
        <div className="rounded-lg border-2 border-border bg-background p-5">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
              <Mic className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">Voice</h2>
              <p className="text-xs text-muted-foreground">
                AI receptionist for your trades business
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void navigate("/setup/voice")}
            className="w-full rounded-md bg-primary py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
          >
            Set up Voice
          </button>
        </div>

        {/* Quote product card — coming soon */}
        <div className="rounded-lg border-2 border-border bg-background p-5 opacity-60">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
              <FileText className="h-5 w-5 text-muted-foreground" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">Quote</h2>
              <p className="text-xs text-muted-foreground">
                Mobile quoting app — coming soon
              </p>
            </div>
          </div>
          <button
            type="button"
            disabled
            className="w-full rounded-md bg-muted py-2 text-sm font-semibold text-muted-foreground cursor-not-allowed"
          >
            Coming soon
          </button>
        </div>
      </div>
    </div>
  );
}

export default SetupPage;
