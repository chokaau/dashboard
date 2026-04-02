/**
 * ResetPasswordPage — confirms the reset password code (story-5-3).
 *
 * Route: /auth/reset-password?email=...
 * On success: navigates to /auth/sign-in.
 */
import { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { confirmResetPassword } from "aws-amplify/auth";

export function ResetPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const emailFromQuery = params.get("email") ?? "";

  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!code || !newPassword) {
      setError("Please fill in all fields.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await confirmResetPassword({
        username: emailFromQuery,
        confirmationCode: code,
        newPassword,
      });
      navigate("/auth/sign-in?reset=success", { replace: true });
    } catch (err) {
      setError((err as Error).message ?? "Password reset failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6">
        <h1 className="text-2xl font-bold text-foreground">Set new password</h1>
        <p className="text-sm text-muted-foreground">
          Enter the code sent to your email and choose a new password.
        </p>

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label htmlFor="reset-code" className="block text-sm font-medium text-foreground">
              Confirmation code
            </label>
            <input
              id="reset-code"
              type="text"
              inputMode="numeric"
              maxLength={6}
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="reset-password" className="block text-sm font-medium text-foreground">
              New password
            </label>
            <input
              id="reset-password"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? "Resetting…" : "Reset password"}
          </button>
        </form>

        <p className="text-center text-sm text-muted-foreground">
          <Link
            to="/auth/sign-in"
            className="text-primary underline underline-offset-2 hover:no-underline"
          >
            Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}

export default ResetPasswordPage;
