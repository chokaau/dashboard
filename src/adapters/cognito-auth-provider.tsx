/**
 * CognitoAuthProvider — skeleton adapter.
 *
 * Configures AWS Amplify v6 and provides the CognitoAuthContext.
 * Wraps children with AuthContextProvider using the Cognito implementation.
 *
 * Story 1.10 — scaffold skeleton (full implementation in story-5-2).
 */
import React from "react";
import { Amplify } from "aws-amplify";

const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID ?? "";
const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID ?? "";

if (userPoolId && clientId) {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId,
        userPoolClientId: clientId,
      },
    },
  });
}

interface CognitoAuthProviderProps {
  children: React.ReactNode;
}

/** Skeleton provider — wired fully in story-5-2. */
export function CognitoAuthProvider({ children }: CognitoAuthProviderProps) {
  return <>{children}</>;
}
