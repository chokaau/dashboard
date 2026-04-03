/**
 * Coverage tests for auth pages not covered by auth-pages.test.tsx:
 * - SignUpPage (invitation-only message)
 * - ConfirmSignUpPage (6-digit code verification)
 * - ResetPasswordPage (new password after reset code)
 *
 * TDD: tests written to cover the uncovered lines flagged by vitest coverage.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// ---------------------------------------------------------------------------
// Amplify auth mocks
// vi.mock is hoisted so we must use vi.fn() inline in the factory,
// then grab refs via vi.mocked() after import.
// ---------------------------------------------------------------------------
vi.mock("aws-amplify/auth", () => ({
  signIn: vi.fn(),
  confirmSignIn: vi.fn(),
  confirmSignUp: vi.fn(),
  resetPassword: vi.fn(),
  confirmResetPassword: vi.fn(),
  signOut: vi.fn(),
  fetchAuthSession: vi.fn(),
  signUp: vi.fn(),
}));

// Mock cognitoSignUp from the auth provider adapter
vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => ({
    isLoaded: true,
    isAuthenticated: false,
    user: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    getAccessToken: vi.fn(),
  }),
  CognitoAuthProvider: ({ children }: { children: React.ReactNode }) => children,
  cognitoSignUp: vi.fn(),
}));

import * as amplifyAuth from "aws-amplify/auth";
import * as authProvider from "@/adapters/cognito-auth-provider";

// Typed refs grabbed after mock is established
const mockConfirmSignUp = vi.mocked(amplifyAuth.confirmSignUp);
const mockConfirmResetPassword = vi.mocked(amplifyAuth.confirmResetPassword);
const mockSignIn = vi.mocked(amplifyAuth.signIn);
const mockFetchAuthSession = vi.mocked(amplifyAuth.fetchAuthSession);
const mockCognitoSignUp = vi.mocked(authProvider.cognitoSignUp);

// ---------------------------------------------------------------------------
// SignUpPage
// ---------------------------------------------------------------------------

import { SignUpPage } from "@/pages/auth/SignUpPage";

function renderSignUp() {
  return render(
    <MemoryRouter initialEntries={["/auth/sign-up"]}>
      <Routes>
        <Route path="/auth/sign-up" element={<SignUpPage />} />
        <Route path="/auth/sign-in" element={<div>SignIn</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("SignUpPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the signup form", () => {
    renderSignUp();
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
  });

  it("shows a link to sign in", () => {
    renderSignUp();
    const link = screen.getByRole("link", { name: /sign in/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/auth/sign-in");
  });
});

// ---------------------------------------------------------------------------
// ConfirmSignUpPage
// ---------------------------------------------------------------------------

import { ConfirmSignUpPage } from "@/pages/auth/ConfirmSignUpPage";

function renderConfirm(search = "?email=owner@example.com") {
  return render(
    <MemoryRouter initialEntries={[`/auth/confirm${search}`]}>
      <Routes>
        <Route path="/auth/confirm" element={<ConfirmSignUpPage />} />
        <Route path="/setup" element={<div>Setup</div>} />
        <Route path="/auth/sign-in" element={<div>SignIn</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ConfirmSignUpPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    sessionStorage.clear();
  });

  it("shows validation error when code length is not 6 digits", async () => {
    renderConfirm();
    // The input has aria-label "6-digit confirmation code"
    const input = screen.getByLabelText(/6-digit confirmation code/i);
    fireEvent.change(input, { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("calls confirmSignUp with correct args on valid 6-digit code", async () => {
    mockConfirmSignUp.mockResolvedValueOnce({});
    // No password in sessionStorage — auto-sign-in skipped
    renderConfirm();

    const input = screen.getByLabelText(/6-digit confirmation code/i);
    fireEvent.change(input, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));

    await waitFor(() => {
      expect(mockConfirmSignUp).toHaveBeenCalledWith({
        username: "owner@example.com",
        confirmationCode: "123456",
      });
    });
  });

  it("navigates to /setup on success", async () => {
    mockConfirmSignUp.mockResolvedValueOnce({});
    // No password in sessionStorage — auto-sign-in skipped
    renderConfirm();

    const input = screen.getByLabelText(/6-digit confirmation code/i);
    fireEvent.change(input, { target: { value: "999999" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));

    await waitFor(() => {
      expect(screen.getByText("Setup")).toBeInTheDocument();
    });
  });

  it("shows error message on confirmSignUp failure", async () => {
    mockConfirmSignUp.mockRejectedValueOnce(new Error("Invalid code"));
    renderConfirm();

    fireEvent.change(screen.getByLabelText(/6-digit confirmation code/i), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/invalid code/i);
    });
  });

  it("shows email field when no email query param", () => {
    // Without ?email=, the email input should be visible
    renderConfirm("");
    expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ResetPasswordPage
// ---------------------------------------------------------------------------

import { ResetPasswordPage } from "@/pages/auth/ResetPasswordPage";

function renderReset(search = "?email=owner@example.com") {
  return render(
    <MemoryRouter initialEntries={[`/auth/reset-password${search}`]}>
      <Routes>
        <Route path="/auth/reset-password" element={<ResetPasswordPage />} />
        <Route path="/auth/sign-in" element={<div>SignIn</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ResetPasswordPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows validation error when fields are empty", async () => {
    renderReset();
    fireEvent.click(screen.getByRole("button", { name: /reset password/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("calls confirmResetPassword with correct args", async () => {
    mockConfirmResetPassword.mockResolvedValueOnce({});
    renderReset();

    fireEvent.change(screen.getByLabelText(/confirmation code/i), {
      target: { value: "654321" },
    });
    fireEvent.change(screen.getByLabelText(/new password/i), {
      target: { value: "NewPass1!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      expect(mockConfirmResetPassword).toHaveBeenCalledWith({
        username: "owner@example.com",
        confirmationCode: "654321",
        newPassword: "NewPass1!",
      });
    });
  });

  it("navigates to sign-in on success", async () => {
    mockConfirmResetPassword.mockResolvedValueOnce({});
    renderReset();

    fireEvent.change(screen.getByLabelText(/confirmation code/i), {
      target: { value: "654321" },
    });
    fireEvent.change(screen.getByLabelText(/new password/i), {
      target: { value: "NewPass1!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText("SignIn")).toBeInTheDocument();
    });
  });

  it("shows error message on confirmResetPassword failure", async () => {
    mockConfirmResetPassword.mockRejectedValueOnce(
      new Error("Expired code.")
    );
    renderReset();

    fireEvent.change(screen.getByLabelText(/confirmation code/i), {
      target: { value: "000000" },
    });
    fireEvent.change(screen.getByLabelText(/new password/i), {
      target: { value: "AnyPass1!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/expired code/i);
    });
  });

  it("shows back-to-sign-in link", () => {
    renderReset();
    const link = screen.getByRole("link", { name: /back to sign in/i });
    expect(link).toHaveAttribute("href", "/auth/sign-in");
  });
});
