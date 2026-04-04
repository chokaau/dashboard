/**
 * SetupPage — product selection (dashboard-10).
 *
 * Replaces the call-forwarding wizard as the /setup entry point.
 * Shows available products: Voice (active) and Quote (coming soon).
 * "Set up Voice" navigates to /setup/voice.
 */
import { useNavigate } from "react-router-dom";
import { Mic, FileText } from "lucide-react";
import { ProductCard } from "@chokaau/ui";

export function SetupPage() {
  const navigate = useNavigate();

  return (
    <div className="mx-auto max-w-md p-6">
      <h1 className="mb-2 text-xl font-semibold text-foreground">Choose a product</h1>
      <p className="mb-8 text-sm text-muted-foreground">
        Select the product you&apos;d like to set up for your business.
      </p>

      <div className="space-y-4">
        <ProductCard
          title="Voice"
          description="AI receptionist for your trades business"
          icon={Mic}
          available={true}
          onSelect={() => void navigate("/setup/voice")}
        />
        <ProductCard
          title="Quote"
          description="Mobile quoting app — coming soon"
          icon={FileText}
          available={false}
        />
      </div>
    </div>
  );
}

export default SetupPage;
