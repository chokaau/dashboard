/**
 * ConfirmSignUpPage — 6-digit code verification (dashboard-9).
 *
 * Route: /auth/confirm
 * After successful confirmSignUp:
 *  1. Auto-sign-in using password from sessionStorage
 *  2. POST to /api/auth/register with business metadata
 *  3. Clear sessionStorage
 *  4. Navigate to /setup
 */
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { confirmSignUp, signIn as amplifySignIn, fetchAuthSession } from "aws-amplify/auth";

// ---------------------------------------------------------------------------
// SessionStorage keys (written by SignUpPage)
// ---------------------------------------------------------------------------

const SS_PASSWORD = "signup_password";
const SS_BUSINESS_NAME = "signup_business_name";
const SS_OWNER_NAME = "signup_owner_name";
const SS_STATE = "signup_state";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function getIdToken(): Promise<string> {
  const session = await fetchAuthSession();
  const token = session.tokens?.idToken?.toString();
  if (!token) throw new Error("No auth token available after sign-in");
  return token;
}

async function callRegister(token: string): Promise<void> {
  const body = {
    business_name: sessionStorage.getItem(SS_BUSINESS_NAME) ?? "",
    owner_name: sessionStorage.getItem(SS_OWNER_NAME) ?? "",
    state: sessionStorage.getItem(SS_STATE) ?? "",
  };
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Registration failed: ${res.status}`);
  }
}

function clearSignupSession(): void {
  sessionStorage.removeItem(SS_PASSWORD);
  sessionStorage.removeItem(SS_BUSINESS_NAME);
  sessionStorage.removeItem(SS_OWNER_NAME);
  sessionStorage.removeItem(SS_STATE);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ConfirmSignUpPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const emailFromQuery = params.get("email") ?? "";

  const [email, setEmail] = useState(emailFromQuery);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!code || code.length !== 6) {
      setError("Please enter the 6-digit confirmation code.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await confirmSignUp({ username: email, confirmationCode: code });

      const password = sessionStorage.getItem(SS_PASSWORD) ?? "";
      if (password) {
        await amplifySignIn({ username: email, password });
        const token = await getIdToken();
        await callRegister(token);
      }

      clearSignupSession();
      navigate("/setup", { replace: true });
    } catch (err) {
      setError((err as Error).message ?? "Confirmation failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        <h1 className="text-2xl font-bold text-foreground">Confirm your account</h1>
        <p className="text-sm text-muted-foreground">
          Enter the 6-digit code sent to your email address.
        </p>

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {!emailFromQuery && (
            <div className="space-y-1">
              <label htmlFor="confirm-email" className="block text-sm font-medium text-foreground">
                Email
              </label>
              <input
                id="confirm-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
          )}
          <div className="space-y-1">
            <label htmlFor="confirm-code" className="block text-sm font-medium text-foreground">
              Confirmation code
            </label>
            <input
              id="confirm-code"
              type="text"
              inputMode="numeric"
              maxLength={6}
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm tracking-widest"
              aria-label="6-digit confirmation code"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? "Confirming…" : "Confirm account"}
          </button>
        </form>
      </div>
    </main>
  );
}

export default ConfirmSignUpPage;
