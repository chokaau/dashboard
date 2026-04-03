/**
 * Tests for dashboard-10: SetupPage (product selection).
 *
 * TDD: RED tests written first. Tests cover:
 * - Renders Voice product card with "Set up Voice" button
 * - Renders Quote "coming soon" card (disabled)
 * - "Set up Voice" navigates to /setup/voice
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
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

import { SetupPage } from "@/pages/SetupPage";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/setup"]}>
      <Routes>
        <Route path="/setup" element={<SetupPage />} />
        <Route path="/setup/voice" element={<div>VoiceWizard</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("SetupPage (product selection)", () => {
  it("renders the Voice product card", () => {
    renderPage();
    // Use heading to identify the Voice card specifically
    expect(screen.getByRole("heading", { name: /^voice$/i })).toBeInTheDocument();
    expect(screen.getByText(/AI receptionist/i)).toBeInTheDocument();
  });

  it("renders the Quote coming-soon card as disabled", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /^quote$/i })).toBeInTheDocument();
    // The disabled button says "Coming soon"
    const comingSoonBtn = screen.getByRole("button", { name: /coming soon/i });
    expect(comingSoonBtn).toBeDisabled();
  });

  it("Set up Voice button navigates to /setup/voice", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /set up voice/i }));
    await waitFor(() => {
      expect(screen.getByText("VoiceWizard")).toBeInTheDocument();
    });
  });
});
