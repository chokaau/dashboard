/**
 * SignUpPage — self-service signup form (dashboard-9).
 *
 * Fields: email, password (min 12 chars + complexity indicator),
 * business name, owner name, state (AU dropdown).
 *
 * On submit:
 *  1. Calls cognitoSignUp
 *  2. Stores business_name, owner_name, state, password in sessionStorage
 *  3. Navigates to /auth/confirm?email=<email>
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { cognitoSignUp } from "@/adapters/cognito-auth-provider";
import { validateEmail } from "@/lib/validation";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const AU_STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"] as const;
const MIN_PASSWORD_LENGTH = 12;

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function validatePassword(v: string): string {
  if (!v) return "Password is required";
  if (v.length < MIN_PASSWORD_LENGTH) return `Password must be at least ${MIN_PASSWORD_LENGTH} characters`;
  return "";
}

function validateName(v: string, label: string): string {
  if (!v.trim()) return `${label} is required`;
  if (v.trim().length < 2) return `${label} must be at least 2 characters`;
  if (v.trim().length > 100) return `${label} must be at most 100 characters`;
  return "";
}

function validateState(v: string): string {
  if (!v) return "State is required";
  return "";
}

// ---------------------------------------------------------------------------
// Password complexity indicator
// ---------------------------------------------------------------------------

type Strength = "weak" | "fair" | "strong";

function getPasswordStrength(v: string): Strength | null {
  if (!v) return null;
  let score = 0;
  if (v.length >= MIN_PASSWORD_LENGTH) score++;
  if (/[A-Z]/.test(v)) score++;
  if (/[0-9]/.test(v)) score++;
  if (/[^A-Za-z0-9]/.test(v)) score++;
  if (score <= 1) return "weak";
  if (score === 2) return "fair";
  return "strong";
}

const STRENGTH_LABEL: Record<Strength, string> = {
  weak: "Weak",
  fair: "Fair",
  strong: "Strong",
};

const STRENGTH_CLASS: Record<Strength, string> = {
  weak: "text-destructive",
  fair: "text-amber-500",
  strong: "text-green-600",
};

// ---------------------------------------------------------------------------
// Error mapping
// ---------------------------------------------------------------------------

function mapSignUpError(err: unknown): string {
  const name = (err as { name?: string }).name;
  if (name === "UsernameExistsException") {
    return "An account with this email already exists. Sign in instead?";
  }
  if (name === "InvalidPasswordException") {
    return "Password does not meet requirements";
  }
  return (err as Error).message ?? "Sign-up failed. Please try again.";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SignUpPage() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [state, setState] = useState("");

  const [errors, setErrors] = useState({
    email: "",
    password: "",
    businessName: "",
    ownerName: "",
    state: "",
  });

  const [globalError, setGlobalError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const passwordStrength = getPasswordStrength(password);

  function validate(): boolean {
    const next = {
      email: validateEmail(email),
      password: validatePassword(password),
      businessName: validateName(businessName, "Business name"),
      ownerName: validateName(ownerName, "Owner name"),
      state: validateState(state),
    };
    setErrors(next);
    return Object.values(next).every((e) => !e);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    setGlobalError("");
    try {
      await cognitoSignUp(email, password, ownerName);
      // Store business metadata only — never store password (SEC-CRED-03)
      sessionStorage.setItem("signup_business_name", businessName);
      sessionStorage.setItem("signup_owner_name", ownerName);
      sessionStorage.setItem("signup_state", state);
      navigate(`/auth/confirm?email=${encodeURIComponent(email)}`);
    } catch (err) {
      setGlobalError(mapSignUpError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-bold text-foreground">Create an account</h1>
          <p className="text-sm text-muted-foreground">
            Get started with Choka
          </p>
        </div>

        {globalError && (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {globalError}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {/* Email */}
          <div className="space-y-1">
            <label htmlFor="email" className="block text-sm font-medium text-foreground">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={() => setErrors((p) => ({ ...p, email: validateEmail(email) }))}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              aria-describedby={errors.email ? "email-error" : undefined}
              aria-invalid={!!errors.email}
            />
            {errors.email && (
              <p id="email-error" role="alert" className="text-xs text-destructive">
                {errors.email}
              </p>
            )}
          </div>

          {/* Password */}
          <div className="space-y-1">
            <label htmlFor="password" className="block text-sm font-medium text-foreground">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onBlur={() => setErrors((p) => ({ ...p, password: validatePassword(password) }))}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              aria-describedby={errors.password ? "password-error" : "password-hint"}
              aria-invalid={!!errors.password}
            />
            {errors.password ? (
              <p id="password-error" role="alert" className="text-xs text-destructive">
                {errors.password}
              </p>
            ) : (
              <p id="password-hint" className="text-xs text-muted-foreground">
                Minimum {MIN_PASSWORD_LENGTH} characters
              </p>
            )}
            {passwordStrength && (
              <p className={`text-xs font-medium ${STRENGTH_CLASS[passwordStrength]}`} aria-label={`Password strength: ${STRENGTH_LABEL[passwordStrength]}`}>
                Strength: {STRENGTH_LABEL[passwordStrength]}
              </p>
            )}
          </div>

          {/* Business name */}
          <div className="space-y-1">
            <label htmlFor="business-name" className="block text-sm font-medium text-foreground">
              Business name
            </label>
            <input
              id="business-name"
              type="text"
              autoComplete="organization"
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
              onBlur={() => setErrors((p) => ({ ...p, businessName: validateName(businessName, "Business name") }))}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              aria-describedby={errors.businessName ? "business-name-error" : undefined}
              aria-invalid={!!errors.businessName}
            />
            {errors.businessName && (
              <p id="business-name-error" role="alert" className="text-xs text-destructive">
                {errors.businessName}
              </p>
            )}
          </div>

          {/* Owner name */}
          <div className="space-y-1">
            <label htmlFor="owner-name" className="block text-sm font-medium text-foreground">
              Owner name
            </label>
            <input
              id="owner-name"
              type="text"
              autoComplete="name"
              value={ownerName}
              onChange={(e) => setOwnerName(e.target.value)}
              onBlur={() => setErrors((p) => ({ ...p, ownerName: validateName(ownerName, "Owner name") }))}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              aria-describedby={errors.ownerName ? "owner-name-error" : undefined}
              aria-invalid={!!errors.ownerName}
            />
            {errors.ownerName && (
              <p id="owner-name-error" role="alert" className="text-xs text-destructive">
                {errors.ownerName}
              </p>
            )}
          </div>

          {/* State */}
          <div className="space-y-1">
            <label htmlFor="state" className="block text-sm font-medium text-foreground">
              State
            </label>
            <select
              id="state"
              value={state}
              onChange={(e) => setState(e.target.value)}
              onBlur={() => setErrors((p) => ({ ...p, state: validateState(state) }))}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              aria-describedby={errors.state ? "state-error" : undefined}
              aria-invalid={!!errors.state}
            >
              <option value="">Select a state</option>
              {AU_STATES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            {errors.state && (
              <p id="state-error" role="alert" className="text-xs text-destructive">
                {errors.state}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link
            to="/auth/sign-in"
            className="text-primary underline underline-offset-2 hover:no-underline"
          >
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}

export default SignUpPage;
