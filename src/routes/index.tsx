/**
 * Application routes (story-5-2).
 *
 * / → redirect to /dashboard
 * /dashboard, /calls, /calls/:id, /profile, /billing, /setup — protected
 * /auth/sign-in, /auth/sign-up, /auth/confirm — public
 */
import { lazy, Suspense } from "react";
import {
  createBrowserRouter,
  Navigate,
  Outlet,
} from "react-router-dom";
import { PageErrorBoundary } from "@/components/error-boundaries/PageErrorBoundary";

// Lazy-loaded pages (code-split per route)
const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const CallHistoryPage = lazy(() => import("@/pages/CallHistoryPage"));
const CallDetailPage = lazy(() => import("@/pages/CallDetailPage"));
const ProfilePage = lazy(() => import("@/pages/ProfilePage"));
const BillingPage = lazy(() => import("@/pages/BillingPage"));
const SetupPage = lazy(() => import("@/pages/SetupPage"));
const SignInPage = lazy(() => import("@/pages/SignInPage"));
const SignUpPage = lazy(() => import("@/pages/SignUpPage"));
const ConfirmPage = lazy(() => import("@/pages/ConfirmPage"));

function PageShell() {
  return (
    <PageErrorBoundary>
      <Suspense fallback={<div className="flex min-h-screen items-center justify-center" aria-label="Loading" />}>
        <Outlet />
      </Suspense>
    </PageErrorBoundary>
  );
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <PageShell />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: <DashboardPage /> },
      { path: "calls", element: <CallHistoryPage /> },
      { path: "calls/:id", element: <CallDetailPage /> },
      { path: "profile", element: <ProfilePage /> },
      { path: "billing", element: <BillingPage /> },
      { path: "setup", element: <SetupPage /> },
      { path: "auth/sign-in", element: <SignInPage /> },
      { path: "auth/sign-up", element: <SignUpPage /> },
      { path: "auth/confirm", element: <ConfirmPage /> },
    ],
  },
]);
