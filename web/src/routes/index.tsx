/**
 * Application routes (story-5-2, updated story-5-3, story-5-10, dashboard-10).
 *
 * / → redirect to /dashboard
 * /dashboard, /calls, /calls/:id, /profile, /billing — protected (AuthGuard)
 * /setup → product selection page (protected)
 * /setup/voice → VoiceSetupWizard (protected)
 * /setup/forwarding → ForwardingSetupWizard (protected, for call-forwarding)
 * /auth/sign-in, /auth/sign-up, /auth/confirm,
 * /auth/forgot-password, /auth/reset-password — public
 */
import { lazy, Suspense } from "react";
import {
  createBrowserRouter,
  Navigate,
  Outlet,
} from "react-router-dom";
import { PageErrorBoundary } from "@/components/error-boundaries/PageErrorBoundary";
import { AuthGuard } from "@/components/AuthGuard";

// Lazy-loaded pages (code-split per route)
const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const CallHistoryPage = lazy(() => import("@/pages/CallHistoryPage"));
const CallDetailPage = lazy(() => import("@/pages/CallDetailPage"));
const ProfilePage = lazy(() => import("@/pages/ProfilePage"));
const BillingPage = lazy(() => import("@/pages/BillingPage"));
const SetupPage = lazy(() => import("@/pages/SetupPage"));
const VoiceSetupWizard = lazy(() => import("@/pages/setup/VoiceSetupWizard"));
const ForwardingSetupWizard = lazy(() => import("@/pages/setup/ForwardingSetupWizard"));

// Auth pages (story-5-3 implementations)
const SignInPage = lazy(() => import("@/pages/auth/SignInPage"));
const SignUpPage = lazy(() => import("@/pages/auth/SignUpPage"));
const ConfirmSignUpPage = lazy(() => import("@/pages/auth/ConfirmSignUpPage"));
const ForgotPasswordPage = lazy(() => import("@/pages/auth/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("@/pages/auth/ResetPasswordPage"));

function PageShell() {
  return (
    <PageErrorBoundary>
      <Suspense fallback={<div className="flex min-h-screen items-center justify-center" aria-label="Loading" />}>
        <Outlet />
      </Suspense>
    </PageErrorBoundary>
  );
}

function ProtectedShell() {
  return (
    <AuthGuard>
      <PageShell />
    </AuthGuard>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <PageShell />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      // Protected routes
      {
        element: <ProtectedShell />,
        children: [
          { path: "dashboard", element: <DashboardPage /> },
          { path: "calls", element: <CallHistoryPage /> },
          { path: "calls/:id", element: <CallDetailPage /> },
          { path: "profile", element: <ProfilePage /> },
          { path: "billing", element: <BillingPage /> },
          { path: "setup", element: <SetupPage /> },
          { path: "setup/voice", element: <VoiceSetupWizard /> },
          { path: "setup/forwarding", element: <ForwardingSetupWizard /> },
        ],
      },
      // Public auth routes
      { path: "auth/sign-in", element: <SignInPage /> },
      { path: "auth/sign-up", element: <SignUpPage /> },
      { path: "auth/confirm", element: <ConfirmSignUpPage /> },
      { path: "auth/forgot-password", element: <ForgotPasswordPage /> },
      { path: "auth/reset-password", element: <ResetPasswordPage /> },
    ],
  },
]);
