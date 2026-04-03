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
      await amplifySignIn({ username, password });
      await loadSession();
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
