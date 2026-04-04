/**
 * ProfilePage — edit business name, AI greeting, notification prefs (story-5-7).
 * Updated dashboard-15: uses @chokaau/ui GreetingPreview, BusinessHoursEditor.
 *
 * Fetches GET /api/profile, saves via PUT /api/profile.
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import {
  InlineError,
  Skeleton,
  GreetingPreview,
  BusinessHoursEditor,
} from "@chokaau/ui";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type NotificationPreference = "all" | "leads_only" | "none";

type DayKey = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

interface DayHours {
  enabled: boolean;
  open: string;
  close: string;
}

type BusinessHours = Record<DayKey, DayHours>;

interface ProfileData {
  businessName: string;
  greeting: string;
  notificationPreference: NotificationPreference;
  services?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DEFAULT_HOURS: BusinessHours = {
  mon: { enabled: true, open: "07:00", close: "17:00" },
  tue: { enabled: true, open: "07:00", close: "17:00" },
  wed: { enabled: true, open: "07:00", close: "17:00" },
  thu: { enabled: true, open: "07:00", close: "17:00" },
  fri: { enabled: true, open: "07:00", close: "17:00" },
  sat: { enabled: false, open: "08:00", close: "12:00" },
  sun: { enabled: false, open: "08:00", close: "12:00" },
};

function parseServicesArray(services: string | undefined): string[] {
  if (!services) return [];
  return services
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

// ---------------------------------------------------------------------------
// Skeleton loader
// ---------------------------------------------------------------------------

function ProfileSkeleton() {
  return (
    <div className="space-y-4 p-6">
      <Skeleton className="h-6 w-32" />
      <Skeleton className="h-10 w-full rounded-md" />
      <Skeleton className="h-6 w-32" />
      <Skeleton className="h-28 w-full rounded-md" />
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-10 w-36 rounded-md" />
    </div>
  );
}

const NOTIFICATION_OPTIONS: { value: NotificationPreference; label: string }[] = [
  { value: "all", label: "SMS for every call" },
  { value: "leads_only", label: "SMS for new leads only" },
  { value: "none", label: "No SMS" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ProfilePage() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<ProfileData>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileData>("/api/profile"),
  });

  const [businessName, setBusinessName] = useState<string | undefined>();
  const [greeting, setGreeting] = useState<string | undefined>();
  const [notificationPreference, setNotificationPreference] = useState<
    NotificationPreference | undefined
  >();
  const [businessHours, setBusinessHours] = useState<BusinessHours>(DEFAULT_HOURS);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Derived form values — fall back to loaded data
  const formBusinessName = businessName ?? data?.businessName ?? "";
  const formGreeting = greeting ?? data?.greeting ?? "";
  const formNotification = notificationPreference ?? data?.notificationPreference ?? "all";
  const formServicesArray = parseServicesArray(data?.services);

  const mutation = useMutation({
    mutationFn: (payload: ProfileData) =>
      apiFetch<ProfileData>("/api/profile", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["profile"], updated);
      setSaveError(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (err: Error) => {
      setSaveError(err.message || "Couldn't save. Try again.");
    },
  });

  if (isLoading) {
    return <ProfileSkeleton />;
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError(null);
    setSaved(false);
    mutation.mutate({
      businessName: formBusinessName,
      greeting: formGreeting,
      notificationPreference: formNotification,
    });
  };

  return (
    <div className="mx-auto max-w-xl p-6">
      <h1 className="mb-6 text-xl font-semibold text-foreground">Profile</h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Business name */}
        <div className="space-y-1.5">
          <label
            htmlFor="businessName"
            className="text-sm font-medium text-foreground"
          >
            Business name
          </label>
          <input
            id="businessName"
            type="text"
            value={formBusinessName}
            onChange={(e) => setBusinessName(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>

        {/* AI greeting */}
        <div className="space-y-1.5">
          <label
            htmlFor="greeting"
            className="text-sm font-medium text-foreground"
          >
            AI Greeting
          </label>
          <textarea
            id="greeting"
            rows={4}
            value={formGreeting}
            onChange={(e) => setGreeting(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>

        {/* Greeting preview */}
        <GreetingPreview
          businessName={formBusinessName}
          services={formServicesArray}
        />

        {/* Business hours editor */}
        <div className="space-y-1.5">
          <p className="text-sm font-medium text-foreground">Business hours</p>
          <BusinessHoursEditor
            hours={businessHours}
            onChange={setBusinessHours}
          />
        </div>

        {/* Notification preferences */}
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-foreground">
            Notification preferences
          </legend>
          {NOTIFICATION_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className="flex cursor-pointer items-center gap-2 text-sm"
            >
              <input
                type="radio"
                name="notificationPreference"
                value={opt.value}
                checked={formNotification === opt.value}
                onChange={() => setNotificationPreference(opt.value)}
                className="accent-primary"
              />
              {opt.label}
            </label>
          ))}
        </fieldset>

        {/* Error */}
        {saveError && <InlineError message={saveError} />}

        {/* Submit */}
        <button
          type="submit"
          disabled={mutation.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {mutation.isPending ? "Saving\u2026" : saved ? "Saved!" : "Save changes"}
        </button>
      </form>
    </div>
  );
}

export default ProfilePage;
