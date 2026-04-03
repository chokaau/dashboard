/**
 * CognitoAuthProvider — full implementation (story-5-2).
 *
 * Configures AWS Amplify v6, listens for auth Hub events, and exposes
 * auth state via CognitoAuthContext. Validates required env vars before
 * configuring; renders <ConfigurationError> if either is missing.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { Amplify } from "aws-amplify";
import {
  confirmSignUp as authConfirmSignUp,
  fetchAuthSession,
  getCurrentUser,
  signIn as amplifySignIn,
  signOut as amplifySignOut,
  signUp as amplifySignUp,
} from "aws-amplify/auth";
import { Hub } from "aws-amplify/utils";
import { ConfigurationError } from "@/components/error-boundaries/ConfigurationError";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthUser {
  username: string;
  tenantSlug: string;
}

export interface AuthContextValue {
  isLoaded: boolean;
  isAuthenticated: boolean;
  user: AuthUser | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  getAccessToken: () => Promise<string>;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const CognitoAuthContext = createContext<AuthContextValue | null>(null);

/**
 * Returns the current auth context. Must be used inside CognitoAuthProvider.
 */
export function useCognitoAuth(): AuthContextValue {
  const ctx = useContext(CognitoAuthContext);
  if (!ctx) {
    throw new Error("useCognitoAuth must be used within CognitoAuthProvider");
  }
  return ctx;
}

/**
 * Returns a stable reference to the current auth context for use outside
 * React components (e.g. apiFetch). Set by CognitoAuthProvider on mount.
 */
let _authContextRef: AuthContextValue | null = null;

export function getAuthContext(): AuthContextValue | null {
  return _authContextRef;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface CognitoAuthProviderProps {
  children: React.ReactNode;
}

export function CognitoAuthProvider({ children }: CognitoAuthProviderProps) {
  const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID ?? "";
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID ?? "";

  // Validate config before attempting to configure Amplify
  const missing: string[] = [];
  if (!userPoolId) missing.push("VITE_COGNITO_USER_POOL_ID");
  if (!clientId) missing.push("VITE_COGNITO_CLIENT_ID");

  if (missing.length > 0) {
    return <ConfigurationError missing={missing} />;
  }

  // Configure Amplify (idempotent — safe to call on re-renders)
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId: clientId,
      },
    },
  });

  return <CognitoAuthProviderInner>{children}</CognitoAuthProviderInner>;
}

// ---------------------------------------------------------------------------
// Stand-alone signUp helper (used by SignUpPage without context)
// ---------------------------------------------------------------------------

/**
 * Registers a new Cognito user. Throws on failure; callers handle errors.
 */
export async function cognitoSignUp(
  email: string,
  password: string,
  name: string
): Promise<void> {
  await amplifySignUp({
    username: email,
    password,
    options: { userAttributes: { email, name } },
  });
}

/**
 * Confirms a Cognito sign-up with a verification code (GEN-ARCH-01).
 * Wraps Amplify directly so callers never import from aws-amplify/auth.
 */
export async function cognitoConfirmSignUp(
  email: string,
  code: string
): Promise<void> {
  await authConfirmSignUp({ username: email, confirmationCode: code });
}

// ---------------------------------------------------------------------------
// Pending registration helpers (SEC-CRED-03)
//
// After email verification, the user signs in normally. If sessionStorage
// holds pending business registration data (but never a password), the
// sign-in flow calls POST /api/auth/register and clears the data.
// ---------------------------------------------------------------------------

const SS_BUSINESS_NAME = "signup_business_name";
const SS_OWNER_NAME = "signup_owner_name";
const SS_STATE = "signup_state";

/**
 * Returns true if pending registration data is present in sessionStorage.
 */
export function hasPendingRegistration(): boolean {
  return !!sessionStorage.getItem(SS_BUSINESS_NAME);
}

/**
 * Reads pending registration data from sessionStorage.
 * Returns null if any required field is missing (GEN-ERR-01).
 */
export function readPendingRegistration(): {
  business_name: string;
  owner_name: string;
  state: string;
} | null {
  const business_name = sessionStorage.getItem(SS_BUSINESS_NAME);
  const owner_name = sessionStorage.getItem(SS_OWNER_NAME);
  const state = sessionStorage.getItem(SS_STATE);
  if (!business_name || !owner_name || !state) return null;
  return { business_name, owner_name, state };
}

/**
 * Clears all pending registration data from sessionStorage.
 */
export function clearPendingRegistration(): void {
  sessionStorage.removeItem(SS_BUSINESS_NAME);
  sessionStorage.removeItem(SS_OWNER_NAME);
  sessionStorage.removeItem(SS_STATE);
}

function CognitoAuthProviderInner({ children }: CognitoAuthProviderProps) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const isMounted = useRef(true);

  const loadSession = useCallback(async () => {
    try {
      const cognitoUser = await getCurrentUser();
      const session = await fetchAuthSession();
      const claims = session.tokens?.idToken?.payload ?? {};
      const tenantSlug =
        (claims["custom:tenant_slug"] as string | undefined) ??
        cognitoUser.username;

      if (isMounted.current) {
        setUser({ username: cognitoUser.username, tenantSlug });
        setIsAuthenticated(true);
      }
    } catch {
      if (isMounted.current) {
        setUser(null);
        setIsAuthenticated(false);
      }
    } finally {
      if (isMounted.current) {
        setIsLoaded(true);
      }
    }
  }, []);

  useEffect(() => {
    isMounted.current = true;
    void loadSession();

    const unlisten = Hub.listen("auth", ({ payload }) => {
      switch (payload.event) {
        case "signedIn":
          void loadSession();
          break;
        case "signedOut":
          if (isMounted.current) {
            setUser(null);
            setIsAuthenticated(false);
          }
          break;
      }
    });

    return () => {
      isMounted.current = false;
      unlisten();
    };
  }, [loadSession]);

  const signIn = useCallback(
    async (username: string, password: string) => {
      const result = await amplifySignIn({ username, password });

      // After sign-in, complete registration if pending data exists (SEC-CRED-03)
      if (hasPendingRegistration()) {
        const pending = readPendingRegistration();
        if (pending) {
          const session = await fetchAuthSession();
          const token = session.tokens?.idToken?.toString();
          if (token) {
            await fetch("/api/auth/register", {
              method: "POST",
              headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify(pending),
            });
          }
          clearPendingRegistration();
        }
      }

      await loadSession();
      return result;
    },
    [loadSession]
  );

  const signOut = useCallback(async () => {
    await amplifySignOut();
    setUser(null);
    setIsAuthenticated(false);
  }, []);

  const getAccessToken = useCallback(async (): Promise<string> => {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    if (!token) throw new Error("No auth token available");
    return token;
  }, []);

  const value: AuthContextValue = {
    isLoaded,
    isAuthenticated,
    user,
    signIn,
    signOut,
    getAccessToken,
  };

  // Expose for apiFetch (outside React tree)
  _authContextRef = value;

  return (
    <CognitoAuthContext.Provider value={value}>
      {children}
    </CognitoAuthContext.Provider>
  );
}
