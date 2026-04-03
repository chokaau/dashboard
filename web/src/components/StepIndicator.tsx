/**
 * StepIndicator — linear progress bar for multi-step wizards (dashboard-10).
 *
 * Props:
 *   totalSteps — number of steps in the wizard
 *   currentStep — 1-based index of the current active step
 */

interface StepIndicatorProps {
  totalSteps: number;
  currentStep: number;
}

export function StepIndicator({ totalSteps, currentStep }: StepIndicatorProps) {
  return (
    <div className="mb-6 flex gap-1" role="progressbar" aria-valuenow={currentStep} aria-valuemax={totalSteps}>
      {Array.from({ length: totalSteps }).map((_, i) => (
        <div
          key={i}
          className={`h-1 flex-1 rounded-full transition-colors ${
            i < currentStep ? "bg-primary" : "bg-muted"
          }`}
        />
      ))}
    </div>
  );
}

export default StepIndicator;
