/**
 * VoiceSetupWizard — 4-step voice service setup wizard (dashboard-10).
 *
 * Step 1: BusinessDetailsStep — business_name, owner_name, state, owner_phone, receptionist_name
 * Step 2: ServicesHoursStep  — services, services_not_offered, service_areas, hours
 * Step 3: PricingPoliciesStep — pricing, policies, faq
 * Step 4: ReviewSubmitStep  — read-only summary, submit for activation
 *
 * On submit:
 *   1. PUT /api/profile with all fields
 *   2. POST /api/activation/request
 *   3. Navigate to /dashboard
 *
 * Pre-fills from GET /api/profile on mount.
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { apiFetch } from "@/lib/api-client";
import { StepIndicator, StepHeader } from "@chokaau/ui";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ProfileData {
  businessName: string;
  ownerName: string;
  receptionistName: string;
  ownerPhone: string;
  services: string;
  servicesNotOffered: string[];
  serviceAreas: string;
  hours: string;
  pricing: string;
  faq: string;
  policies: string;
  aboutOwner: string;
  state: string;
  setupComplete: boolean;
}

export interface WizardFormData {
  businessName: string;
  ownerName: string;
  state: string;
  ownerPhone: string;
  receptionistName: string;
  services: string;
  servicesNotOffered: string; // comma-separated in UI, split on submit
  serviceAreas: string;
  hours: string;
  pricing: string;
  policies: string;
  faq: string;
}

export type StepErrors = Partial<Record<keyof WizardFormData, string>>;

const TOTAL_STEPS = 4;

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

/** Australian mobile/landline: starts with 04, 02-09, or +61. Any spacing allowed. */
const AU_PHONE_RE = /^(\+61|0)[2-9]\d[\d\s]{6,}$/;

function validatePhone(value: string): string | undefined {
  if (!value.trim()) return undefined; // ownerPhone is not required
  if (!AU_PHONE_RE.test(value.replace(/\s/g, ""))) {
    return "Enter a valid Australian number, e.g. 0412 345 678 or +61412345678";
  }
  return undefined;
}

function validateStep1(data: WizardFormData): StepErrors {
  const errors: StepErrors = {};
  if (!data.businessName.trim()) errors.businessName = "Business name is required";
  if (!data.ownerName.trim()) errors.ownerName = "Owner name is required";
  if (!data.state.trim()) errors.state = "State is required";
  if (!data.receptionistName.trim()) errors.receptionistName = "Receptionist name is required";
  const phoneErr = validatePhone(data.ownerPhone);
  if (phoneErr) errors.ownerPhone = phoneErr;
  return errors;
}

function validateStep2(data: WizardFormData): StepErrors {
  const errors: StepErrors = {};
  if (!data.services.trim()) errors.services = "Services offered is required";
  if (!data.serviceAreas.trim()) errors.serviceAreas = "Service areas is required";
  if (!data.hours.trim()) errors.hours = "Business hours is required";
  return errors;
}

function validateStep3(data: WizardFormData): StepErrors {
  const errors: StepErrors = {};
  if (!data.pricing.trim()) errors.pricing = "Pricing information is required";
  return errors;
}

function validateStep(step: number, data: WizardFormData): StepErrors {
  if (step === 1) return validateStep1(data);
  if (step === 2) return validateStep2(data);
  if (step === 3) return validateStep3(data);
  return {};
}

// ---------------------------------------------------------------------------
// Field component
// ---------------------------------------------------------------------------

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      {children}
      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

const inputClass =
  "w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary";
const inputErrorClass =
  "w-full rounded-md border border-destructive bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-destructive";
const textareaClass = `${inputClass} resize-y`;
const textareaErrorClass = `${inputErrorClass} resize-y`;

// ---------------------------------------------------------------------------
// Step 1: Business Details
// ---------------------------------------------------------------------------

interface Step1Props {
  data: WizardFormData;
  errors: StepErrors;
  onChange: (patch: Partial<WizardFormData>) => void;
}

function BusinessDetailsStep({ data, errors, onChange }: Step1Props) {
  return (
    <>
      <StepHeader step={1} totalSteps={TOTAL_STEPS} title="Business details" />
      <div className="space-y-4">
        <Field id="businessName" label="Business name" error={errors.businessName}>
          <input
            id="businessName"
            type="text"
            value={data.businessName}
            onChange={(e) => onChange({ businessName: e.target.value })}
            className={errors.businessName ? inputErrorClass : inputClass}
            aria-invalid={!!errors.businessName}
          />
        </Field>
        <Field id="ownerName" label="Owner name" error={errors.ownerName}>
          <input
            id="ownerName"
            type="text"
            value={data.ownerName}
            onChange={(e) => onChange({ ownerName: e.target.value })}
            className={errors.ownerName ? inputErrorClass : inputClass}
            aria-invalid={!!errors.ownerName}
          />
        </Field>
        <Field id="state" label="State" error={errors.state}>
          <input
            id="state"
            type="text"
            value={data.state}
            onChange={(e) => onChange({ state: e.target.value })}
            className={errors.state ? inputErrorClass : inputClass}
            placeholder="e.g. VIC"
            aria-invalid={!!errors.state}
          />
        </Field>
        <Field
          id="ownerPhone"
          label="Phone number"
          error={errors.ownerPhone}
        >
          <input
            id="ownerPhone"
            type="tel"
            value={data.ownerPhone}
            onChange={(e) => onChange({ ownerPhone: e.target.value })}
            className={errors.ownerPhone ? inputErrorClass : inputClass}
            placeholder="e.g. 0412 345 678"
            aria-invalid={!!errors.ownerPhone}
            aria-describedby="ownerPhone-hint"
          />
          {!errors.ownerPhone && (
            <p id="ownerPhone-hint" className="text-xs text-muted-foreground">
              Australian format, e.g. 0412 345 678 or +61412345678
            </p>
          )}
        </Field>
        <Field id="receptionistName" label="What should your AI receptionist be called?" error={errors.receptionistName}>
          <input
            id="receptionistName"
            type="text"
            value={data.receptionistName}
            onChange={(e) => onChange({ receptionistName: e.target.value })}
            className={errors.receptionistName ? inputErrorClass : inputClass}
            placeholder="e.g. Choka"
            aria-invalid={!!errors.receptionistName}
          />
        </Field>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Step 2: Services & Hours
// ---------------------------------------------------------------------------

interface Step2Props {
  data: WizardFormData;
  errors: StepErrors;
  onChange: (patch: Partial<WizardFormData>) => void;
}

function ServicesHoursStep({ data, errors, onChange }: Step2Props) {
  return (
    <>
      <StepHeader step={2} totalSteps={TOTAL_STEPS} title="Services & hours" />
      <div className="space-y-4">
        <Field id="services" label="Services offered" error={errors.services}>
          <textarea
            id="services"
            rows={3}
            value={data.services}
            onChange={(e) => onChange({ services: e.target.value })}
            className={errors.services ? textareaErrorClass : textareaClass}
            placeholder="Describe the services your business offers"
            aria-invalid={!!errors.services}
          />
        </Field>
        <Field id="servicesNotOffered" label="Services NOT offered (comma-separated)">
          <input
            id="servicesNotOffered"
            type="text"
            value={data.servicesNotOffered}
            onChange={(e) => onChange({ servicesNotOffered: e.target.value })}
            className={inputClass}
            placeholder="e.g. Solar panels, Air conditioning"
          />
        </Field>
        <Field id="serviceAreas" label="Service areas" error={errors.serviceAreas}>
          <textarea
            id="serviceAreas"
            rows={2}
            value={data.serviceAreas}
            onChange={(e) => onChange({ serviceAreas: e.target.value })}
            className={errors.serviceAreas ? textareaErrorClass : textareaClass}
            placeholder="e.g. Melbourne metro and surrounding suburbs"
            aria-invalid={!!errors.serviceAreas}
          />
        </Field>
        <Field id="hours" label="Business hours" error={errors.hours}>
          <textarea
            id="hours"
            rows={2}
            value={data.hours}
            onChange={(e) => onChange({ hours: e.target.value })}
            className={errors.hours ? textareaErrorClass : textareaClass}
            placeholder="e.g. Mon-Fri 7am-5pm, Sat 8am-12pm"
            aria-invalid={!!errors.hours}
          />
        </Field>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Step 3: Pricing & Policies
// ---------------------------------------------------------------------------

interface Step3Props {
  data: WizardFormData;
  errors: StepErrors;
  onChange: (patch: Partial<WizardFormData>) => void;
}

function PricingPoliciesStep({ data, errors, onChange }: Step3Props) {
  return (
    <>
      <StepHeader step={3} totalSteps={TOTAL_STEPS} title="Pricing & policies" />
      <div className="space-y-4">
        <Field id="pricing" label="Pricing information" error={errors.pricing}>
          <textarea
            id="pricing"
            rows={3}
            value={data.pricing}
            onChange={(e) => onChange({ pricing: e.target.value })}
            className={errors.pricing ? textareaErrorClass : textareaClass}
            placeholder="Describe your pricing or call-out fees"
            aria-invalid={!!errors.pricing}
          />
        </Field>
        <Field id="policies" label="Policies (optional)">
          <textarea
            id="policies"
            rows={3}
            value={data.policies}
            onChange={(e) => onChange({ policies: e.target.value })}
            className={textareaClass}
            placeholder="e.g. No call-out fee within 20km"
          />
        </Field>
        <Field id="faq" label="FAQ (optional)">
          <textarea
            id="faq"
            rows={3}
            value={data.faq}
            onChange={(e) => onChange({ faq: e.target.value })}
            className={textareaClass}
            placeholder="Common questions and answers"
          />
        </Field>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Step 4: Review & Submit
// ---------------------------------------------------------------------------

interface ReviewRowProps {
  label: string;
  value: string;
}

function ReviewRow({ label, value }: ReviewRowProps) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-border py-2 last:border-0">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="text-sm text-foreground">{value || "—"}</span>
    </div>
  );
}

interface Step4Props {
  data: WizardFormData;
  onSubmit: () => void;
  isSubmitting: boolean;
  submitError: string | null;
}

function ReviewSubmitStep({ data, onSubmit, isSubmitting, submitError }: Step4Props) {
  return (
    <>
      <StepHeader step={4} totalSteps={TOTAL_STEPS} title="Review your details" />
      <div className="space-y-0">
        <ReviewRow label="Business name" value={data.businessName} />
        <ReviewRow label="Owner name" value={data.ownerName} />
        <ReviewRow label="State" value={data.state} />
        <ReviewRow label="Phone number" value={data.ownerPhone} />
        <ReviewRow label="Receptionist name" value={data.receptionistName} />
        <ReviewRow label="Services" value={data.services} />
        <ReviewRow label="Services not offered" value={data.servicesNotOffered} />
        <ReviewRow label="Service areas" value={data.serviceAreas} />
        <ReviewRow label="Hours" value={data.hours} />
        <ReviewRow label="Pricing" value={data.pricing} />
      </div>
      {submitError && (
        <p className="mt-4 text-sm text-destructive">{submitError}</p>
      )}
      <button
        type="button"
        onClick={onSubmit}
        disabled={isSubmitting}
        className="mt-6 w-full rounded-md bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        {isSubmitting ? "Submitting\u2026" : "Submit for activation"}
      </button>
    </>
  );
}

// ---------------------------------------------------------------------------
// Main wizard component
// ---------------------------------------------------------------------------

function toProfilePayload(data: WizardFormData) {
  return {
    business_name: data.businessName,
    owner_name: data.ownerName,
    receptionist_name: data.receptionistName,
    owner_phone: data.ownerPhone,
    services: data.services,
    services_not_offered: data.servicesNotOffered
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    service_areas: data.serviceAreas,
    hours: data.hours,
    pricing: data.pricing,
    faq: data.faq,
    policies: data.policies,
    about_owner: "",
    state: data.state,
  };
}

function fromProfile(p: ProfileData): WizardFormData {
  return {
    businessName: p.businessName,
    ownerName: p.ownerName,
    state: p.state,
    ownerPhone: p.ownerPhone,
    receptionistName: p.receptionistName,
    services: p.services,
    servicesNotOffered: (p.servicesNotOffered ?? []).join(", "),
    serviceAreas: p.serviceAreas,
    hours: p.hours,
    pricing: p.pricing,
    policies: p.policies,
    faq: p.faq,
  };
}

const emptyForm: WizardFormData = {
  businessName: "",
  ownerName: "",
  state: "",
  ownerPhone: "",
  receptionistName: "",
  services: "",
  servicesNotOffered: "",
  serviceAreas: "",
  hours: "",
  pricing: "",
  policies: "",
  faq: "",
};

export function VoiceSetupWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState<WizardFormData>(emptyForm);
  const [stepErrors, setStepErrors] = useState<StepErrors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [initialised, setInitialised] = useState(false);

  const { isLoading, data: profileData } = useQuery<ProfileData>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileData>("/api/profile"),
  });

  // Pre-fill form once profile data loads (runs only on first successful fetch)
  useEffect(() => {
    if (profileData && !initialised) {
      setFormData(fromProfile(profileData));
      setInitialised(true);
    }
  }, [profileData, initialised]);

  const submitMutation = useMutation({
    mutationFn: async () => {
      await apiFetch("/api/profile", {
        method: "PUT",
        body: JSON.stringify(toProfilePayload(formData)),
      });
      await apiFetch("/api/activation/request", { method: "POST" });
    },
    onSuccess: () => {
      void navigate("/dashboard");
    },
    onError: (err: Error) => {
      setSubmitError(err.message || "Submission failed. Please try again.");
    },
  });

  const handleChange = (patch: Partial<WizardFormData>) => {
    setFormData((prev) => ({ ...prev, ...patch }));
    // Clear errors for changed fields
    setStepErrors((prev) => {
      const next = { ...prev };
      for (const key of Object.keys(patch) as (keyof WizardFormData)[]) {
        delete next[key];
      }
      return next;
    });
  };

  const handleNext = () => {
    const errors = validateStep(step, formData);
    if (Object.keys(errors).length > 0) {
      setStepErrors(errors);
      return;
    }
    setStepErrors({});
    if (step < TOTAL_STEPS) setStep((s) => s + 1);
  };

  const handleBack = () => {
    setStepErrors({});
    if (step > 1) setStep((s) => s - 1);
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-md p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 w-24 rounded bg-muted" />
          <div className="h-8 w-48 rounded bg-muted" />
          <div className="h-10 rounded bg-muted" />
          <div className="h-10 rounded bg-muted" />
          <div className="h-10 rounded bg-muted" />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md p-6">
      {/* Top nav */}
      <div className="mb-4 flex items-center justify-between">
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
        <span className="text-sm text-muted-foreground">Voice setup</span>
        <div className="w-16" />
      </div>

      <StepIndicator totalSteps={TOTAL_STEPS} currentStep={step} />

      {/* Step content */}
      <div className="min-h-64">
        {step === 1 && (
          <BusinessDetailsStep data={formData} errors={stepErrors} onChange={handleChange} />
        )}
        {step === 2 && (
          <ServicesHoursStep data={formData} errors={stepErrors} onChange={handleChange} />
        )}
        {step === 3 && (
          <PricingPoliciesStep data={formData} errors={stepErrors} onChange={handleChange} />
        )}
        {step === 4 && (
          <ReviewSubmitStep
            data={formData}
            onSubmit={() => submitMutation.mutate()}
            isSubmitting={submitMutation.isPending}
            submitError={submitError}
          />
        )}
      </div>

      {/* Next button (hidden on step 4 — submit button replaces it) */}
      {step < TOTAL_STEPS && (
        <button
          type="button"
          onClick={handleNext}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-md bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
          aria-label="Next"
        >
          Next
          <ArrowRight className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

export default VoiceSetupWizard;
