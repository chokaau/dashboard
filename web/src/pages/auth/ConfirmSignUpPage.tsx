/**
 * ConfirmSignUpPage — 6-digit code verification (dashboard-9).
 *
 * Route: /auth/confirm
 * After successful confirmSignUp:
 *  1. Redirects to /auth/sign-in?verified=true (SEC-CRED-03)
 *  2. Registration completes transparently after sign-in via the auth provider
 *
 * Never performs auto-sign-in; password is never stored in sessionStorage.
 */
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { cognitoConfirmSignUp } from "@/adapters/cognito-auth-provider";

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

    const targetEmail = email.trim();
    if (!targetEmail) {
      setError("Registration incomplete. Please sign up again.");
      navigate("/auth/sign-up", { replace: true });
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      await cognitoConfirmSignUp(targetEmail, code);
      navigate("/auth/sign-in?verified=true", { replace: true });
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
