/**
 * Tests for ForwardingSetupWizard — moved from story-5-9 SetupPage.
 *
 * The old SetupPage (call-forwarding wizard) is now at /setup/forwarding
 * via ForwardingSetupWizard.tsx. The /setup route now shows product selection.
 *
 * Tests cover:
 * - Step 1: carrier selection renders 4 options
 * - Selecting a carrier enables Next button
 * - Next advances to step 2
 * - Back on step 2 returns to step 1
 * - Step progress indicator shows current step
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => ({
    isLoaded: true,
    isAuthenticated: true,
    user: { username: "owner", tenantSlug: "acme" },
    signOut: vi.fn(),
    getAccessToken: vi.fn().mockResolvedValue("tok"),
  }),
}));

import { ForwardingSetupWizard } from "@/pages/setup/ForwardingSetupWizard";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/setup/forwarding"]}>
      <Routes>
        <Route path="/setup/forwarding" element={<ForwardingSetupWizard />} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ForwardingSetupWizard (formerly SetupPage)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders step 1 with 4 carrier options", () => {
    renderPage();
    expect(screen.getByText(/telstra/i)).toBeInTheDocument();
    expect(screen.getByText(/optus/i)).toBeInTheDocument();
    expect(screen.getByText(/vodafone/i)).toBeInTheDocument();
    expect(screen.getByText(/other/i)).toBeInTheDocument();
  });

  it("shows step 1 of 4 progress indicator", () => {
    renderPage();
    expect(screen.getByText(/step 1/i)).toBeInTheDocument();
  });

  it("Next button is disabled until a carrier is selected", () => {
    renderPage();
    const nextBtn = screen.getByRole("button", { name: /next/i });
    expect(nextBtn).toBeDisabled();
  });

  it("Next button enables after carrier selection", () => {
    renderPage();
    fireEvent.click(screen.getByText(/telstra/i));
    const nextBtn = screen.getByRole("button", { name: /next/i });
    expect(nextBtn).not.toBeDisabled();
  });

  it("clicking Next advances to step 2", () => {
    renderPage();
    fireEvent.click(screen.getByText(/telstra/i));
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText(/step 2/i)).toBeInTheDocument();
  });

  it("Back button on step 2 returns to step 1", async () => {
    renderPage();
    fireEvent.click(screen.getByText(/telstra/i));
    fireEvent.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 2/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /back/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 1/i)).toBeInTheDocument();
    });
  });
});
