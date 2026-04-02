/**
 * ForgotPasswordPage — sends password reset code (story-5-3).
 *
 * Route: /auth/forgot-password
 * On success: navigates to /auth/reset-password?email=...
 */
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { resetPassword } from "aws-amplify/auth";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) {
      setEmailError("Email is required");
      return;
    }
    if (!EMAIL_RE.test(email)) {
      setEmailError("Invalid email address");
      return;
    }
    setEmailError("");
    setSubmitting(true);
    setError("");
    try {
      await resetPassword({ username: email });
      navigate(`/auth/reset-password?email=${encodeURIComponent(email)}`, {
        replace: true,
      });
    } catch (err) {
      setError((err as Error).message ?? "Failed to send reset code.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        <h1 className="text-2xl font-bold text-foreground">Reset password</h1>
        <p className="text-sm text-muted-foreground">
          Enter your email address and we&apos;ll send you a reset code.
        </p>

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="space-y-1">
            <label htmlFor="forgot-email" className="block text-sm font-medium text-foreground">
              Email
            </label>
            <input
              id="forgot-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onBlur={() => {
                if (email && !EMAIL_RE.test(email)) {
                  setEmailError("Invalid email address");
                }
              }}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              aria-describedby={emailError ? "forgot-email-error" : undefined}
              aria-invalid={!!emailError}
            />
            {emailError && (
              <p id="forgot-email-error" role="alert" className="text-xs text-destructive">
                {emailError}
              </p>
            )}
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? "Sending…" : "Send reset code"}
          </button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          Remember your password?{" "}
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

export default ForgotPasswordPage;
