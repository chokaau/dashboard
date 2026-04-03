/**
 * SignInPage — Amplify v6 headless sign-in with TOTP + FORCE_CHANGE_PASSWORD support.
 *
 * story-5-3
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { confirmSignIn } from "aws-amplify/auth";
import { useCognitoAuth } from "@/adapters/cognito-auth-provider";

// ---------------------------------------------------------------------------
// Validation helpers
// ---------------------------------------------------------------------------

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validateEmail(value: string): string {
  if (!value.trim()) return "Email is required";
  if (!EMAIL_RE.test(value)) return "Invalid email address";
  return "";
}

function validatePassword(value: string): string {
  if (!value) return "Password is required";
  return "";
}

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
  const { signIn } = useCognitoAuth();

  // Credentials step
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailError, setEmailError] = useState("");
  const [passwordError, setPasswordError] = useState("");

  // TOTP step
  const [totpCode, setTotpCode] = useState("");
  const [totpError, setTotpError] = useState("");

  // New password step
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordError, setNewPasswordError] = useState("");

  const [step, setStep] = useState<Step>("credentials");
  const [submitting, setSubmitting] = useState(false);
  const [globalError, setGlobalError] = useState("");

  // ------------------------------------------------------------------
  // Credentials submit
  // ------------------------------------------------------------------

  async function handleSignIn(e: React.FormEvent) {
    e.preventDefault();
    const eErr = validateEmail(email);
    const pErr = validatePassword(password);
    setEmailError(eErr);
    setPasswordError(pErr);
    if (eErr || pErr) return;

    setSubmitting(true);
    setGlobalError("");
    try {
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
    } catch (err) {
      setGlobalError((err as Error).message ?? "Sign-in failed. Please try again.");
    } finally {
      setSubmitting(false);
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

  // Default: credentials step
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-bold text-foreground">Sign in</h1>
          <p className="text-sm text-muted-foreground">
            Welcome back to Choka
          </p>
        </div>

        {globalError && (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {globalError}
          </p>
        )}

        <form onSubmit={handleSignIn} className="space-y-4" noValidate>
          <div className="space-y-1">
            <label
              htmlFor="email"
              className="block text-sm font-medium text-foreground"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={() => setEmailError(validateEmail(email))}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              aria-describedby={emailError ? "email-error" : undefined}
              aria-invalid={!!emailError}
            />
            {emailError && (
              <p id="email-error" role="alert" className="text-xs text-destructive">
                {emailError}
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label
              htmlFor="password"
              className="block text-sm font-medium text-foreground"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onBlur={() => setPasswordError(validatePassword(password))}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              aria-describedby={passwordError ? "password-error" : undefined}
              aria-invalid={!!passwordError}
            />
            {passwordError && (
              <p id="password-error" role="alert" className="text-xs text-destructive">
                {passwordError}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="text-center text-sm">
          <a
            href="/auth/forgot-password"
            className="text-primary underline underline-offset-2 hover:no-underline"
          >
            Forgot password?
          </a>
        </div>

        <p className="text-center text-sm text-muted-foreground">
          Don&apos;t have an account?{" "}
          <Link
            to="/auth/sign-up"
            className="text-primary underline underline-offset-2 hover:no-underline"
          >
            Sign up
          </Link>
        </p>
      </div>
    </main>
  );
}

export default SignInPage;
