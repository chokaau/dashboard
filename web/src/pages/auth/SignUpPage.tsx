/**
 * SignUpPage — invitation-only message (story-5-3).
 *
 * Admin-only registration: no sign-up form shown.
 */
import { Link } from "react-router-dom";

export function SignUpPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6 text-center">
        <h1 className="text-2xl font-bold text-foreground">Create an account</h1>
        <p className="text-muted-foreground">
          Account creation is by invitation only. Contact support to get started.
        </p>
        <p className="text-sm text-muted-foreground">
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
