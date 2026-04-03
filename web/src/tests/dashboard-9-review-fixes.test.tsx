/**
 * Tests for dashboard-9 review fixes:
 *
 * SEC-CRED-03 — password never stored in sessionStorage
 * GEN-ERR-01  — missing sessionStorage shows user-friendly redirect
 * GEN-ARCH-01 — ConfirmSignUpPage uses cognitoConfirmSignUp (not direct Amplify)
 * GEN-MAINT-02 — email validation imported from shared lib/validation
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockSignIn = vi.fn();
const mockCognitoSignUp = vi.fn();
const mockCognitoConfirmSignUp = vi.fn();

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

vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => ({
    isLoaded: true,
    isAuthenticated: false,
    user: null,
    signIn: mockSignIn,
    signOut: vi.fn(),
    getAccessToken: vi.fn(),
  }),
  CognitoAuthProvider: ({ children }: { children: React.ReactNode }) => children,
  cognitoSignUp: (...args: unknown[]) => mockCognitoSignUp(...args),
  cognitoConfirmSignUp: (...args: unknown[]) => mockCognitoConfirmSignUp(...args),
}));

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------

import { SignUpPage } from "@/pages/auth/SignUpPage";
import { ConfirmSignUpPage } from "@/pages/auth/ConfirmSignUpPage";
import { SignInPage } from "@/pages/auth/SignInPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderSignUp() {
  return render(
    <MemoryRouter initialEntries={["/auth/sign-up"]}>
      <Routes>
        <Route path="/auth/sign-up" element={<SignUpPage />} />
        <Route path="/auth/confirm" element={<div>ConfirmPage</div>} />
        <Route path="/auth/sign-in" element={<div>SignInPage</div>} />
      </Routes>
    </MemoryRouter>
  );
}

function renderConfirm(email = "user@example.com") {
  return render(
    <MemoryRouter initialEntries={[`/auth/confirm?email=${encodeURIComponent(email)}`]}>
      <Routes>
        <Route path="/auth/confirm" element={<ConfirmSignUpPage />} />
        <Route path="/auth/sign-in" element={<div>SignIn reached</div>} />
        <Route path="/auth/sign-up" element={<div>SignUp reached</div>} />
      </Routes>
    </MemoryRouter>
  );
}

function renderSignIn(search = "") {
  return render(
    <MemoryRouter initialEntries={[`/auth/sign-in${search}`]}>
      <Routes>
        <Route path="/auth/sign-in" element={<SignInPage />} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
      </Routes>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// SEC-CRED-03: password never stored in sessionStorage by SignUpPage
// ---------------------------------------------------------------------------

describe("SEC-CRED-03: SignUpPage — no password in sessionStorage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("does NOT set signup_password in sessionStorage on successful signup", async () => {
    mockCognitoSignUp.mockResolvedValueOnce(undefined);
    renderSignUp();

    await userEvent.type(screen.getByLabelText(/email/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "SecureP@ss123!");
    await userEvent.type(screen.getByLabelText(/business name/i), "Acme Co");
    await userEvent.type(screen.getByLabelText(/owner name/i), "Jane Smith");
    await userEvent.selectOptions(screen.getByLabelText(/state/i), "NSW");

    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(screen.getByText("ConfirmPage")).toBeInTheDocument();
    });

    expect(sessionStorage.getItem("signup_password")).toBeNull();
  });

  it("DOES store business_name, owner_name, state in sessionStorage", async () => {
    mockCognitoSignUp.mockResolvedValueOnce(undefined);
    renderSignUp();

    await userEvent.type(screen.getByLabelText(/email/i), "owner@example.com");
    await userEvent.type(screen.getByLabelText(/^password$/i), "SecureP@ss123!");
    await userEvent.type(screen.getByLabelText(/business name/i), "Acme Co");
    await userEvent.type(screen.getByLabelText(/owner name/i), "Jane Smith");
    await userEvent.selectOptions(screen.getByLabelText(/state/i), "VIC");

    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(screen.getByText("ConfirmPage")).toBeInTheDocument();
    });

    expect(sessionStorage.getItem("signup_business_name")).toBe("Acme Co");
    expect(sessionStorage.getItem("signup_owner_name")).toBe("Jane Smith");
    expect(sessionStorage.getItem("signup_state")).toBe("VIC");
  });
});

// ---------------------------------------------------------------------------
// GEN-ARCH-01: ConfirmSignUpPage uses cognitoConfirmSignUp (not Amplify direct)
// ---------------------------------------------------------------------------

describe("GEN-ARCH-01: ConfirmSignUpPage uses provider abstraction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("calls cognitoConfirmSignUp (not amplify.confirmSignUp directly)", async () => {
    mockCognitoConfirmSignUp.mockResolvedValueOnce(undefined);
    renderConfirm("user@example.com");

    fireEvent.change(screen.getByLabelText(/6-digit confirmation code/i), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));

    await waitFor(() => {
      expect(mockCognitoConfirmSignUp).toHaveBeenCalledWith(
        "user@example.com",
        "123456"
      );
    });
  });

  it("redirects to /auth/sign-in?verified=true after successful confirmation", async () => {
    mockCognitoConfirmSignUp.mockResolvedValueOnce(undefined);
    renderConfirm("user@example.com");

    fireEvent.change(screen.getByLabelText(/6-digit confirmation code/i), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));

    await waitFor(() => {
      expect(screen.getByText("SignIn reached")).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// GEN-ERR-01: Missing sessionStorage — user-friendly redirect
// ---------------------------------------------------------------------------

describe("GEN-ERR-01: ConfirmSignUpPage — missing email redirects to sign-up", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it("redirects to /auth/sign-up when email is empty and submitted", async () => {
    render(
      <MemoryRouter initialEntries={["/auth/confirm"]}>
        <Routes>
          <Route path="/auth/confirm" element={<ConfirmSignUpPage />} />
          <Route path="/auth/sign-up" element={<div>SignUp reached</div>} />
          <Route path="/auth/sign-in" element={<div>SignIn reached</div>} />
        </Routes>
      </MemoryRouter>
    );

    // Type a valid 6-digit code (email field visible since no query param)
    const emailInput = screen.getByLabelText(/^email$/i);
    // Leave email empty, type a code
    fireEvent.change(screen.getByLabelText(/6-digit confirmation code/i), {
      target: { value: "123456" },
    });
    // Clear email to simulate missing data
    fireEvent.change(emailInput, { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: /confirm account/i }));

    await waitFor(() => {
      expect(screen.getByText("SignUp reached")).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// SEC-CRED-03 + GEN-MAINT-02: SignInPage — verified banner + shared validation
// ---------------------------------------------------------------------------

describe("SignInPage — verified=true banner (SEC-CRED-03)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows verified success banner when ?verified=true is in URL", () => {
    renderSignIn("?verified=true");
    expect(
      screen.getByText(/email verified/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/sign in to complete your account setup/i)
    ).toBeInTheDocument();
  });

  it("does NOT show verified banner without ?verified=true", () => {
    renderSignIn();
    expect(screen.queryByText(/email verified/i)).not.toBeInTheDocument();
  });

  it("verified banner has role=status", () => {
    renderSignIn("?verified=true");
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// GEN-MAINT-02: shared validateEmail used in both SignUpPage and SignInPage
// ---------------------------------------------------------------------------

describe("GEN-MAINT-02: shared email validation", () => {
  it("SignInPage shows invalid email error from shared validator", async () => {
    renderSignIn();
    await userEvent.type(screen.getByLabelText(/email/i), "notanemail");
    fireEvent.blur(screen.getByLabelText(/email/i));
    await waitFor(() => {
      expect(screen.getByText(/invalid email address/i)).toBeInTheDocument();
    });
  });

  it("SignUpPage shows invalid email error from shared validator", async () => {
    renderSignUp();
    await userEvent.type(screen.getByLabelText(/email/i), "notanemail");
    fireEvent.blur(screen.getByLabelText(/email/i));
    await waitFor(() => {
      expect(screen.getByText(/invalid email address/i)).toBeInTheDocument();
    });
  });
});
