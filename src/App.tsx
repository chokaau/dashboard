/**
 * App root — full provider + router wiring (story-5-2).
 *
 * Provider order (outer → inner):
 *   AppErrorBoundary → QueryClientProvider → CognitoAuthProvider → RouterProvider
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { AppErrorBoundary } from "@/components/error-boundaries/AppErrorBoundary";
import { CognitoAuthProvider } from "@/adapters/cognito-auth-provider";
import { queryClient } from "@/lib/query-client";
import { router } from "@/routes/index";

export default function App() {
  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <CognitoAuthProvider>
          <RouterProvider router={router} />
        </CognitoAuthProvider>
      </QueryClientProvider>
    </AppErrorBoundary>
  );
}
