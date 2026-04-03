/**
 * AuthGuard — wraps protected routes (story-5-10).
 *
 * - While auth is loading: renders nothing (avoids flash of protected content)
 * - Not authenticated: redirects to /auth/sign-in
 * - Authenticated: renders children
 */
import { Navigate } from "react-router-dom";
import { useCognitoAuth } from "@/adapters/cognito-auth-provider";

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { isLoaded, isAuthenticated } = useCognitoAuth();

  // Still initialising — render nothing to avoid flash
  if (!isLoaded) {
    return null;
  }

  // Not signed in — redirect to sign-in
  if (!isAuthenticated) {
    return <Navigate to="/auth/sign-in" replace />;
  }

  return <>{children}</>;
}

export default AuthGuard;
