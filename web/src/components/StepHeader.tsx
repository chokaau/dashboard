/**
 * StepHeader — step label + title used in multi-step wizards (dashboard-10).
 *
 * Props:
 *   step       — current 1-based step number
 *   totalSteps — total number of steps in the wizard
 *   title      — human-readable step title
 */

interface StepHeaderProps {
  step: number;
  totalSteps: number;
  title: string;
}

export function StepHeader({ step, totalSteps, title }: StepHeaderProps) {
  return (
    <div className="mb-6">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Step {step} of {totalSteps}
      </p>
      <h1 className="mt-1 text-lg font-semibold text-foreground">{title}</h1>
    </div>
  );
}

export default StepHeader;
