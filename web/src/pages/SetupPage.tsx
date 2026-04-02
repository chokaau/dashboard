/**
 * SetupPage — 4-step call forwarding setup wizard (story-5-9).
 *
 * Step 1: Select carrier (Telstra / Optus / Vodafone / Other)
 * Step 2: Disable voicemail (instructions)
 * Step 3: Activate forwarding (dial code shown)
 * Step 4: Confirm & test
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, CheckCircle } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Carrier = "telstra" | "optus" | "vodafone" | "other";

const CARRIERS: { id: Carrier; label: string }[] = [
  { id: "telstra", label: "Telstra" },
  { id: "optus", label: "Optus" },
  { id: "vodafone", label: "Vodafone" },
  { id: "other", label: "Other" },
];

// Forwarding codes per carrier (dial to forward unanswered calls)
const FORWARD_CODES: Record<Carrier, string> = {
  telstra: "**61*<CHOKA_NUMBER>%23",
  optus: "**61*<CHOKA_NUMBER>%23",
  vodafone: "**61*<CHOKA_NUMBER>%23",
  other: "**61*<CHOKA_NUMBER>%23",
};

const TOTAL_STEPS = 4;

// ---------------------------------------------------------------------------
// Step components
// ---------------------------------------------------------------------------

function StepHeader({ step, title }: { step: number; title: string }) {
  return (
    <div className="mb-6">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Step {step} of {TOTAL_STEPS}
      </p>
      <h1 className="mt-1 text-lg font-semibold text-foreground">{title}</h1>
    </div>
  );
}

function Step1CarrierSelect({
  selected,
  onSelect,
}: {
  selected: Carrier | null;
  onSelect: (c: Carrier) => void;
}) {
  return (
    <>
      <StepHeader step={1} title="Who is your phone provider?" />
      <div className="grid grid-cols-2 gap-3">
        {CARRIERS.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => onSelect(c.id)}
            className={`rounded-lg border-2 px-4 py-5 text-sm font-medium transition-colors ${
              selected === c.id
                ? "border-primary bg-primary/5 text-primary"
                : "border-border bg-background text-foreground hover:border-primary/40"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>
    </>
  );
}

function Step2DisableVoicemail({ carrier }: { carrier: Carrier }) {
  return (
    <>
      <StepHeader step={2} title="First, turn off voicemail" />
      <p className="mb-4 text-sm text-muted-foreground">
        Before we can answer your calls, voicemail needs to be off.
      </p>
      <ol className="space-y-3 text-sm">
        <li className="flex gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
            1
          </span>
          Open your phone dialer
        </li>
        <li className="flex gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
            2
          </span>
          <span>
            Dial{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
              {carrier === "telstra" ? "##002#" : "##002#"}
            </code>{" "}
            and press call
          </span>
        </li>
        <li className="flex gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
            3
          </span>
          Wait for the confirmation message
        </li>
      </ol>
    </>
  );
}

function Step3ActivateForwarding({ carrier }: { carrier: Carrier }) {
  const code = FORWARD_CODES[carrier];
  return (
    <>
      <StepHeader step={3} title="Activate call forwarding" />
      <p className="mb-4 text-sm text-muted-foreground">
        Now set your phone to forward unanswered calls to Choka.
      </p>
      <ol className="space-y-3 text-sm">
        <li className="flex gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
            1
          </span>
          Open your phone dialer
        </li>
        <li className="flex gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
            2
          </span>
          <span>
            Dial{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
              {code}
            </code>{" "}
            and press call
          </span>
        </li>
        <li className="flex gap-2">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
            3
          </span>
          Wait for the confirmation message
        </li>
      </ol>
    </>
  );
}

function Step4Confirm() {
  return (
    <>
      <StepHeader step={4} title="You're all set!" />
      <div className="flex flex-col items-center py-6 text-center">
        <CheckCircle className="mb-3 h-12 w-12 text-green-500" />
        <p className="text-sm text-muted-foreground">
          Call forwarding is active. Choka will now answer your unanswered
          calls.
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          Test it by calling your number from another phone.
        </p>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SetupPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [carrier, setCarrier] = useState<Carrier | null>(null);

  const canNext =
    step === 1 ? carrier !== null : step < TOTAL_STEPS;

  const handleNext = () => {
    if (step < TOTAL_STEPS) setStep((s) => s + 1);
    else void navigate("/dashboard");
  };

  const handleBack = () => {
    if (step > 1) setStep((s) => s - 1);
  };

  return (
    <div className="mx-auto max-w-md p-6">
      {/* Top nav */}
      <div className="mb-6 flex items-center justify-between">
        <button
          type="button"
          onClick={handleBack}
          disabled={step === 1}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground disabled:opacity-0"
          aria-label="Back"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
        <span className="text-sm text-muted-foreground">
          Set up call forwarding
        </span>
        <div className="w-16" />
      </div>

      {/* Progress bar */}
      <div className="mb-6 flex gap-1">
        {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors ${
              i < step ? "bg-primary" : "bg-muted"
            }`}
          />
        ))}
      </div>

      {/* Step content */}
      <div className="min-h-64">
        {step === 1 && (
          <Step1CarrierSelect
            selected={carrier}
            onSelect={setCarrier}
          />
        )}
        {step === 2 && <Step2DisableVoicemail carrier={carrier ?? "other"} />}
        {step === 3 && <Step3ActivateForwarding carrier={carrier ?? "other"} />}
        {step === 4 && <Step4Confirm />}
      </div>

      {/* Next / Done button */}
      <button
        type="button"
        onClick={handleNext}
        disabled={!canNext}
        className="mt-6 flex w-full items-center justify-center gap-2 rounded-md bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
        aria-label={step === TOTAL_STEPS ? "Go to dashboard" : "Next"}
      >
        {step === TOTAL_STEPS ? "Go to dashboard" : (
          <>
            Next
            <ArrowRight className="h-4 w-4" />
          </>
        )}
      </button>
    </div>
  );
}

export default SetupPage;
