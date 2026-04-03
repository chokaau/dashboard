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
const mockFetchAuthSession = vi.fn();
const mockSignUp = vi.fn();

vi.mock("aws-amplify/auth", () => ({
  signIn: mockSignIn,
  confirmSignIn: mockConfirmSignIn,
  confirmSignUp: mockConfirmSignUp,
  resetPassword: mockResetPassword,
  confirmResetPassword: mockConfirmResetPassword,
  signOut: mockSignOut,
  fetchAuthSession: mockFetchAuthSession,
  signUp: mockSignUp,
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

const mockCognitoSignUp = vi.fn();

vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => mockAuthContext,
  CognitoAuthProvider: ({ children }: { children: React.ReactNode }) => children,
  cognitoSignUp: (...args: unknown[]) => mockCognitoSignUp(...args),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderWithRouter(ui: React.ReactElement, initialPath = "/auth/sign-in") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/auth/sign-in" element={ui} />
        <Route path="/auth/sign-up" element={ui} />
        <Route path="/auth/confirm" element={<div>ConfirmPage</div>} />
        <Route path="/auth/forgot-password" element={<div>ForgotPasswordPage</div>} />
        <Route path="/auth/reset-password" element={<div>ResetPasswordPage</div>} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
        <Route path="/setup" element={<div>Setup</div>} />
      </Routes>
    </MemoryRouter>
  );
}

function renderSignUpWithRouter() {
  return render(
    <MemoryRouter initialEntries={["/auth/sign-up"]}>
      <Routes>
        <Route path="/auth/sign-up" element={<SignUpPageComponent />} />
        <Route path="/auth/sign-in" element={<div>SignInPage</div>} />
        <Route path="/auth/confirm" element={<div>ConfirmPage</div>} />
      </Routes>
    </MemoryRouter>
  );
}

// Lazy component refs for SignUpPage and ConfirmSignUpPage
let SignUpPageComponent: React.ComponentType;
let ConfirmSignUpPageComponent: React.ComponentType;

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

  it("shows a Sign up link pointing to /auth/sign-up", async () => {
    const { SignInPage } = await import("@/pages/auth/SignInPage");
    renderWithRouter(<SignInPage />);
    const link = screen.getByRole("link", { name: /sign up/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/auth/sign-up");
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
  beforeEach(async () => {
    vi.clearAllMocks();
    const mod = await import("@/pages/auth/SignUpPage");
    SignUpPageComponent = mod.SignUpPage;
  });

  it("renders all required form fields", () => {
    renderSignUpWithRouter();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/business name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/owner name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/state/i)).toBeInTheDocument();
  });

  it("shows validation errors when form is submitted empty", async () => {
    renderSignUpWithRouter();
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() => {
      expect(screen.getByText(/email is required/i)).toBeInTheDocument();
      expect(screen.getByText(/password is required/i)).toBeInTheDocument();
      expect(screen.getByText(/business name is required/i)).toBeInTheDocument();
      expect(screen.getByText(/owner name is required/i)).toBeInTheDocument();
      expect(screen.getByText(/state is required/i)).toBeInTheDocument();
    });
  });

  it("shows password length error when password is too short", async () => {
    renderSignUpWithRouter();
    await userEvent.type(screen.getByLabelText(/^password$/i), "short");
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() => {
      expect(screen.getByText(/at least 12 characters/i)).toBeInTheDocument();
    });
  });

  it("calls cognitoSignUp with email, password, ownerName on valid submit", async () => {
    mockCognitoSignUp.mockResolvedValueOnce(undefined);
    renderSignUpWithRouter();

    await userEvent.type(screen.getByLabelText(/email/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "SecureP@ss123!");
    await userEvent.type(screen.getByLabelText(/business name/i), "Acme Co");
    await userEvent.type(screen.getByLabelText(/owner name/i), "Jane Smith");
    await userEvent.selectOptions(screen.getByLabelText(/state/i), "NSW");

    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(mockCognitoSignUp).toHaveBeenCalledWith(
        "owner@example.com",
        "SecureP@ss123!",
        "Jane Smith"
      );
    });
  });

  it("navigates to /auth/confirm after successful signup", async () => {
    mockCognitoSignUp.mockResolvedValueOnce(undefined);
    renderSignUpWithRouter();

    await userEvent.type(screen.getByLabelText(/email/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "SecureP@ss123!");
    await userEvent.type(screen.getByLabelText(/business name/i), "Acme Co");
    await userEvent.type(screen.getByLabelText(/owner name/i), "Jane Smith");
    await userEvent.selectOptions(screen.getByLabelText(/state/i), "VIC");

    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(screen.getByText("ConfirmPage")).toBeInTheDocument();
    });
  });

  it("shows UsernameExistsException error message", async () => {
    const err = Object.assign(new Error("User already exists"), {
      name: "UsernameExistsException",
    });
    mockCognitoSignUp.mockRejectedValueOnce(err);
    renderSignUpWithRouter();

    await userEvent.type(screen.getByLabelText(/email/i), "exists@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "SecureP@ss123!");
    await userEvent.type(screen.getByLabelText(/business name/i), "Acme Co");
    await userEvent.type(screen.getByLabelText(/owner name/i), "Jane Smith");
    await userEvent.selectOptions(screen.getByLabelText(/state/i), "QLD");

    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/account with this email already exists/i)
      ).toBeInTheDocument();
    });
  });

  it("shows InvalidPasswordException error message", async () => {
    const err = Object.assign(new Error("Password does not conform to policy"), {
      name: "InvalidPasswordException",
    });
    mockCognitoSignUp.mockRejectedValueOnce(err);
    renderSignUpWithRouter();

    await userEvent.type(screen.getByLabelText(/email/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "SecureP@ss123!");
    await userEvent.type(screen.getByLabelText(/business name/i), "Acme Co");
    await userEvent.type(screen.getByLabelText(/owner name/i), "Jane Smith");
    await userEvent.selectOptions(screen.getByLabelText(/state/i), "WA");

    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/password does not meet requirements/i)
      ).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// ConfirmSignUpPage tests
// ---------------------------------------------------------------------------

describe("ConfirmSignUpPage", () => {
  beforeEach(async () => {
    vi.resetAllMocks();
    sessionStorage.clear();
    const mod = await import("@/pages/auth/ConfirmSignUpPage");
    ConfirmSignUpPageComponent = mod.ConfirmSignUpPage;
  });

  function renderConfirmPage(email = "test@example.com") {
    return render(
      <MemoryRouter initialEntries={[`/auth/confirm?email=${encodeURIComponent(email)}`]}>
        <Routes>
          <Route path="/auth/confirm" element={<ConfirmSignUpPageComponent />} />
          <Route path="/setup" element={<div>Setup reached</div>} />
        </Routes>
      </MemoryRouter>
    );
  }

  it("renders confirmation code input", () => {
    renderConfirmPage();
    expect(screen.getByLabelText(/6-digit confirmation code/i)).toBeInTheDocument();
  });

  it("shows validation error when code is not 6 digits", async () => {
    renderConfirmPage();
    await userEvent.type(screen.getByLabelText(/6-digit confirmation code/i), "123");
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/6-digit/i);
    });
  });

  it("calls confirmSignUp with email and code", async () => {
    // No password in sessionStorage — auto-sign-in is skipped, no fetch needed
    mockConfirmSignUp.mockResolvedValueOnce({ isSignUpComplete: true });

    renderConfirmPage("user@example.com");

    await userEvent.type(screen.getByLabelText(/6-digit confirmation code/i), "123456");
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));

    await waitFor(() => {
      expect(mockConfirmSignUp).toHaveBeenCalledWith({
        username: "user@example.com",
        confirmationCode: "123456",
      });
    });
  });

  it("auto-signs-in and calls register when password is in sessionStorage", async () => {
    sessionStorage.setItem("signup_password", "TestPass123!");
    sessionStorage.setItem("signup_business_name", "Acme");
    sessionStorage.setItem("signup_owner_name", "Jane");
    sessionStorage.setItem("signup_state", "NSW");

    mockConfirmSignUp.mockResolvedValueOnce({ isSignUpComplete: true });
    mockSignIn.mockResolvedValueOnce({ isSignedIn: true });
    mockFetchAuthSession.mockResolvedValueOnce({
      tokens: { idToken: { toString: () => "tok-abc" } },
    });
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: true });

    renderConfirmPage("user@example.com");

    await userEvent.type(screen.getByLabelText(/6-digit confirmation code/i), "654321");
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));

    await waitFor(() => {
      expect(mockSignIn).toHaveBeenCalledWith({
        username: "user@example.com",
        password: "TestPass123!",
      });
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/auth/register",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({ Authorization: "Bearer tok-abc" }),
        })
      );
    });
  });

  it("clears sessionStorage and navigates to /setup on success", async () => {
    sessionStorage.setItem("signup_password", "TestPass123!");
    mockConfirmSignUp.mockResolvedValueOnce({ isSignUpComplete: true });
    mockSignIn.mockResolvedValueOnce({ isSignedIn: true });
    mockFetchAuthSession.mockResolvedValueOnce({
      tokens: { idToken: { toString: () => "tok-xyz" } },
    });
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: true });

    renderConfirmPage("user@example.com");

    await userEvent.type(screen.getByLabelText(/6-digit confirmation code/i), "999888");
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));

    await waitFor(() => {
      expect(screen.getByText("Setup reached")).toBeInTheDocument();
      expect(sessionStorage.getItem("signup_password")).toBeNull();
    });
  });

  it("shows error when confirmSignUp fails", async () => {
    mockConfirmSignUp.mockRejectedValueOnce(new Error("Invalid verification code"));

    renderConfirmPage("user@example.com");

    await userEvent.type(screen.getByLabelText(/6-digit confirmation code/i), "000000");
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/invalid verification code/i);
    });
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
