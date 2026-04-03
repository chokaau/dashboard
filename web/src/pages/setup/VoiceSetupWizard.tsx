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
import { StepIndicator } from "@/components/StepIndicator";

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

const TOTAL_STEPS = 4;

// ---------------------------------------------------------------------------
// Step header
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

// ---------------------------------------------------------------------------
// Field components
// ---------------------------------------------------------------------------

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

const inputClass =
  "w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary";
const textareaClass = `${inputClass} resize-y`;

// ---------------------------------------------------------------------------
// Step 1: Business Details
// ---------------------------------------------------------------------------

interface Step1Props {
  data: WizardFormData;
  onChange: (patch: Partial<WizardFormData>) => void;
}

function BusinessDetailsStep({ data, onChange }: Step1Props) {
  return (
    <>
      <StepHeader step={1} title="Business details" />
      <div className="space-y-4">
        <Field id="businessName" label="Business name">
          <input
            id="businessName"
            type="text"
            value={data.businessName}
            onChange={(e) => onChange({ businessName: e.target.value })}
            className={inputClass}
          />
        </Field>
        <Field id="ownerName" label="Owner name">
          <input
            id="ownerName"
            type="text"
            value={data.ownerName}
            onChange={(e) => onChange({ ownerName: e.target.value })}
            className={inputClass}
          />
        </Field>
        <Field id="state" label="State">
          <input
            id="state"
            type="text"
            value={data.state}
            onChange={(e) => onChange({ state: e.target.value })}
            className={inputClass}
            placeholder="e.g. VIC"
          />
        </Field>
        <Field id="ownerPhone" label="Phone number (E.164 format, e.g. +61412000001)">
          <input
            id="ownerPhone"
            type="tel"
            value={data.ownerPhone}
            onChange={(e) => onChange({ ownerPhone: e.target.value })}
            className={inputClass}
            placeholder="+61412000001"
          />
        </Field>
        <Field id="receptionistName" label="What should your AI receptionist be called?">
          <input
            id="receptionistName"
            type="text"
            value={data.receptionistName}
            onChange={(e) => onChange({ receptionistName: e.target.value })}
            className={inputClass}
            placeholder="e.g. Choka"
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
  onChange: (patch: Partial<WizardFormData>) => void;
}

function ServicesHoursStep({ data, onChange }: Step2Props) {
  return (
    <>
      <StepHeader step={2} title="Services & hours" />
      <div className="space-y-4">
        <Field id="services" label="Services offered">
          <textarea
            id="services"
            rows={3}
            value={data.services}
            onChange={(e) => onChange({ services: e.target.value })}
            className={textareaClass}
            placeholder="Describe the services your business offers"
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
        <Field id="serviceAreas" label="Service areas">
          <textarea
            id="serviceAreas"
            rows={2}
            value={data.serviceAreas}
            onChange={(e) => onChange({ serviceAreas: e.target.value })}
            className={textareaClass}
            placeholder="e.g. Melbourne metro and surrounding suburbs"
          />
        </Field>
        <Field id="hours" label="Business hours">
          <textarea
            id="hours"
            rows={2}
            value={data.hours}
            onChange={(e) => onChange({ hours: e.target.value })}
            className={textareaClass}
            placeholder="e.g. Mon-Fri 7am-5pm, Sat 8am-12pm"
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
  onChange: (patch: Partial<WizardFormData>) => void;
}

function PricingPoliciesStep({ data, onChange }: Step3Props) {
  return (
    <>
      <StepHeader step={3} title="Pricing & policies" />
      <div className="space-y-4">
        <Field id="pricing" label="Pricing information">
          <textarea
            id="pricing"
            rows={3}
            value={data.pricing}
            onChange={(e) => onChange({ pricing: e.target.value })}
            className={textareaClass}
            placeholder="Describe your pricing or call-out fees"
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

interface ReviewRow {
  label: string;
  value: string;
}

function ReviewRow({ label, value }: ReviewRow) {
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
      <StepHeader step={4} title="Review your details" />
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
  };

  const handleNext = () => {
    if (step < TOTAL_STEPS) setStep((s) => s + 1);
  };

  const handleBack = () => {
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
          <BusinessDetailsStep data={formData} onChange={handleChange} />
        )}
        {step === 2 && (
          <ServicesHoursStep data={formData} onChange={handleChange} />
        )}
        {step === 3 && (
          <PricingPoliciesStep data={formData} onChange={handleChange} />
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
