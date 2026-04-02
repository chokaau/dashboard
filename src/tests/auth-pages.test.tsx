/**
 * Tests for story-5-3: Auth pages — SignIn, SignUp, Confirm, Forgot/Reset Password.
 *
 * TDD: RED tests written first. Tests cover:
 * - Empty email shows validation error on submit
 * - Wrong password shows Amplify error inline
 * - Successful signIn navigates to /dashboard
 * - TOTP challenge shows TOTP input
 * - TOTP NotAuthorizedException shows inline error
 * - SignUpPage shows invitation-only message
 * - ConfirmSignUpPage submits 6-digit code
 * - ForgotPasswordPage sends reset code
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// ---------------------------------------------------------------------------
// Amplify auth mocks
// ---------------------------------------------------------------------------
const mockSignIn = vi.fn();
const mockConfirmSignIn = vi.fn();
const mockConfirmSignUp = vi.fn();
const mockResetPassword = vi.fn();
const mockConfirmResetPassword = vi.fn();
const mockSignOut = vi.fn();

vi.mock("aws-amplify/auth", () => ({
  signIn: mockSignIn,
  confirmSignIn: mockConfirmSignIn,
  confirmSignUp: mockConfirmSignUp,
  resetPassword: mockResetPassword,
  confirmResetPassword: mockConfirmResetPassword,
  signOut: mockSignOut,
}));

// Mock the auth context — default unauthenticated
const mockAuthContext = {
  isLoaded: true,
  isAuthenticated: false,
  user: null,
  signIn: vi.fn(),
  signOut: mockSignOut,
  getAccessToken: vi.fn(),
};

vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => mockAuthContext,
  CognitoAuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderWithRouter(ui: React.ReactElement, initialPath = "/auth/sign-in") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/auth/sign-in" element={ui} />
        <Route path="/auth/sign-up" element={<div>SignUpPage</div>} />
        <Route path="/auth/confirm" element={<div>ConfirmPage</div>} />
        <Route path="/auth/forgot-password" element={<div>ForgotPasswordPage</div>} />
        <Route path="/auth/reset-password" element={<div>ResetPasswordPage</div>} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
        <Route path="/setup" element={<div>Setup</div>} />
      </Routes>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// SignInPage tests
// ---------------------------------------------------------------------------

describe("SignInPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows validation error when email is empty on submit", async () => {
    const { SignInPage } = await import("@/pages/auth/SignInPage");
    renderWithRouter(<SignInPage />);

    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText(/email is required/i)).toBeInTheDocument();
    });
  });

  it("shows validation error for invalid email format", async () => {
    const { SignInPage } = await import("@/pages/auth/SignInPage");
    renderWithRouter(<SignInPage />);

    await userEvent.type(screen.getByLabelText(/email/i), "notanemail");
    fireEvent.blur(screen.getByLabelText(/email/i));

    await waitFor(() => {
      expect(screen.getByText(/invalid email/i)).toBeInTheDocument();
    });
  });

  it("shows Amplify error inline when signIn fails", async () => {
    mockAuthContext.signIn.mockRejectedValueOnce(
      new Error("Incorrect username or password.")
    );
    const { SignInPage } = await import("@/pages/auth/SignInPage");
    renderWithRouter(<SignInPage />);

    await userEvent.type(screen.getByLabelText(/email/i), "user@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "wrongpass");
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/incorrect username or password/i)
      ).toBeInTheDocument();
    });
  });

  it("navigates to /dashboard on successful signIn", async () => {
    mockAuthContext.signIn.mockResolvedValueOnce({ isSignedIn: true });
    const { SignInPage } = await import("@/pages/auth/SignInPage");

    render(
      <MemoryRouter initialEntries={["/auth/sign-in"]}>
        <Routes>
          <Route path="/auth/sign-in" element={<SignInPage />} />
          <Route path="/dashboard" element={<div>Dashboard reached</div>} />
        </Routes>
      </MemoryRouter>
    );

    await userEvent.type(screen.getByLabelText(/email/i), "user@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "correct-pass");
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText("Dashboard reached")).toBeInTheDocument();
    });
  });

  it("shows TOTP input when signIn returns TOTP challenge", async () => {
    mockAuthContext.signIn.mockResolvedValueOnce({
      isSignedIn: false,
      nextStep: { signInStep: "CONFIRM_SIGN_IN_WITH_TOTP_CODE" },
    });
    const { SignInPage } = await import("@/pages/auth/SignInPage");
    renderWithRouter(<SignInPage />);

    await userEvent.type(screen.getByLabelText(/email/i), "user@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "pass");
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/enter your authenticator code/i)
      ).toBeInTheDocument();
    });
  });

  it("shows inline error when TOTP code is incorrect (NotAuthorizedException)", async () => {
    // First call: signIn succeeds with TOTP challenge
    mockAuthContext.signIn.mockResolvedValueOnce({
      isSignedIn: false,
      nextStep: { signInStep: "CONFIRM_SIGN_IN_WITH_TOTP_CODE" },
    });
    // confirmSignIn rejects with NotAuthorizedException
    mockConfirmSignIn.mockRejectedValueOnce(
      Object.assign(new Error("Incorrect code. Try again."), {
        name: "NotAuthorizedException",
      })
    );

    const { SignInPage } = await import("@/pages/auth/SignInPage");
    renderWithRouter(<SignInPage />);

    await userEvent.type(screen.getByLabelText(/email/i), "user@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "pass");
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    // Wait for TOTP step
    await waitFor(() => {
      expect(
        screen.getByText(/enter your authenticator code/i)
      ).toBeInTheDocument();
    });

    // Enter TOTP code and submit
    await userEvent.type(screen.getByLabelText(/authenticator code/i), "123456");
    fireEvent.click(screen.getByRole("button", { name: /verify/i }));

    await waitFor(() => {
      // Error may appear in both the alert banner and the field hint
      expect(
        screen.getAllByText(/incorrect code/i).length
      ).toBeGreaterThan(0);
    });
  });
});

// ---------------------------------------------------------------------------
// SignUpPage tests
// ---------------------------------------------------------------------------

describe("SignUpPage", () => {
  it("shows invitation-only message", async () => {
    const { SignUpPage } = await import("@/pages/auth/SignUpPage");
    render(
      <MemoryRouter>
        <SignUpPage />
      </MemoryRouter>
    );
    expect(
      screen.getByText(/invitation only/i)
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ForgotPasswordPage tests
// ---------------------------------------------------------------------------

describe("ForgotPasswordPage", () => {
  it("calls resetPassword with the entered email", async () => {
    mockResetPassword.mockResolvedValueOnce({
      nextStep: { resetPasswordStep: "CONFIRM_RESET_PASSWORD_WITH_CODE" },
    });
    const { ForgotPasswordPage } = await import(
      "@/pages/auth/ForgotPasswordPage"
    );
    render(
      <MemoryRouter initialEntries={["/auth/forgot-password"]}>
        <Routes>
          <Route path="/auth/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/auth/reset-password" element={<div>ResetPassword</div>} />
        </Routes>
      </MemoryRouter>
    );

    await userEvent.type(screen.getByLabelText(/email/i), "user@example.com");
    fireEvent.click(screen.getByRole("button", { name: /send reset/i }));

    await waitFor(() => {
      expect(mockResetPassword).toHaveBeenCalledWith({
        username: "user@example.com",
      });
    });
  });
});
