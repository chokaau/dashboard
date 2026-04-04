/**
 * SignInPage — Amplify v6 headless sign-in with TOTP + FORCE_CHANGE_PASSWORD support.
 *
 * Credentials step rendered by <SignInUI> from @chokaau/ui.
 * TOTP and new-password steps remain inline.
 *
 * story-5-3
 */
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { confirmSignIn } from "aws-amplify/auth";
import { SignInPage as SignInUI } from "@chokaau/ui";
import { useCognitoAuth } from "@/adapters/cognito-auth-provider";

// ---------------------------------------------------------------------------
// Step types
// ---------------------------------------------------------------------------

type Step =
  | "credentials"
  | "totp"
  | "new_password";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SignInPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isVerified = searchParams.get("verified") === "true";
  const { signIn } = useCognitoAuth();

  // TOTP step
  const [totpCode, setTotpCode] = useState("");
  const [totpError, setTotpError] = useState("");

  // New password step
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordError, setNewPasswordError] = useState("");

  const [step, setStep] = useState<Step>("credentials");
  const [submitting, setSubmitting] = useState(false);

  // ------------------------------------------------------------------
  // Credentials submit — passed as onSubmit to SignInUI
  // ------------------------------------------------------------------

  async function handleSignIn({ email, password }: { email: string; password: string }) {
    const result = await signIn(email, password);
    const next = (result as { nextStep?: { signInStep: string } } | undefined)
      ?.nextStep?.signInStep;

    if (next === "CONFIRM_SIGN_IN_WITH_TOTP_CODE") {
      setStep("totp");
    } else if (next === "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED") {
      setStep("new_password");
    } else {
      navigate("/dashboard", { replace: true });
    }
  }

  // ------------------------------------------------------------------
  // TOTP submit
  // ------------------------------------------------------------------

  async function handleTotpVerify(e: React.FormEvent) {
    e.preventDefault();
    if (!totpCode.trim()) {
      setTotpError("Code is required");
      return;
    }
    setSubmitting(true);
    setTotpError("");
    try {
      await confirmSignIn({ challengeResponse: totpCode });
      navigate("/dashboard", { replace: true });
    } catch (err) {
      const name = (err as { name?: string }).name;
      if (name === "NotAuthorizedException") {
        setTotpError("Incorrect code. Try again.");
      } else {
        setTotpError((err as Error).message ?? "Verification failed.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  // ------------------------------------------------------------------
  // New password submit
  // ------------------------------------------------------------------

  async function handleNewPassword(e: React.FormEvent) {
    e.preventDefault();
    if (!newPassword) {
      setNewPasswordError("New password is required");
      return;
    }
    setSubmitting(true);
    setNewPasswordError("");
    try {
      await confirmSignIn({ challengeResponse: newPassword });
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setNewPasswordError((err as Error).message ?? "Failed to set new password.");
    } finally {
      setSubmitting(false);
    }
  }

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  if (step === "totp") {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center p-6">
        <div className="w-full max-w-sm space-y-6">
          <h1 className="text-2xl font-bold text-foreground">
            Enter your authenticator code
          </h1>
          <p className="text-sm text-muted-foreground">
            Open your authenticator app and enter the 6-digit code.
          </p>
          {totpError && (
            <p role="alert" className="text-sm text-destructive">
              {totpError}
            </p>
          )}
          <form onSubmit={handleTotpVerify} className="space-y-4">
            <div className="space-y-1">
              <label
                htmlFor="totp-code"
                className="block text-sm font-medium text-foreground"
              >
                Authenticator code
              </label>
              <input
                id="totp-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                aria-describedby={totpError ? "totp-error" : undefined}
              />
              {totpError && (
                <p id="totp-error" className="text-xs text-destructive">
                  {totpError}
                </p>
              )}
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {submitting ? "Verifying…" : "Verify"}
            </button>
          </form>
          <button
            type="button"
            onClick={() => {
              void (async () => {
                try { await import("aws-amplify/auth").then(m => m.signOut()); } catch { /* ignore */ }
                setStep("credentials");
                setTotpCode("");
                setTotpError("");
              })();
            }}
            className="text-sm text-muted-foreground underline underline-offset-2"
          >
            Use a different account
          </button>
        </div>
      </main>
    );
  }

  if (step === "new_password") {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center p-6">
        <div className="w-full max-w-sm space-y-6">
          <h1 className="text-2xl font-bold text-foreground">Set new password</h1>
          <p className="text-sm text-muted-foreground">
            You must set a new password before continuing.
          </p>
          <form onSubmit={handleNewPassword} className="space-y-4">
            <div className="space-y-1">
              <label
                htmlFor="new-password"
                className="block text-sm font-medium text-foreground"
              >
                New password
              </label>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
              {newPasswordError && (
                <p className="text-xs text-destructive">{newPasswordError}</p>
              )}
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {submitting ? "Saving…" : "Set password"}
            </button>
          </form>
        </div>
      </main>
    );
  }

  // Default: credentials step — rendered by SignInUI from @chokaau/ui.
  // The verified banner is shown above the UI component.
  return (
    <div>
      {isVerified && (
        <div className="fixed top-0 inset-x-0 z-50 flex justify-center px-4 pt-4">
          <p
            role="status"
            className="rounded-md border border-green-500/40 bg-green-500/10 px-4 py-2 text-sm text-green-700 dark:text-green-400 shadow"
          >
            Email verified! Sign in to complete your account setup.
          </p>
        </div>
      )}
      <SignInUI onSubmit={handleSignIn} />
    </div>
  );
}

export default SignInPage;
