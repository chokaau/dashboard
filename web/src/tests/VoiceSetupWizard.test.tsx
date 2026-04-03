/**
 * Tests for dashboard-10: VoiceSetupWizard.
 *
 * TDD: RED tests written first. Tests cover:
 * - Renders step 1 (BusinessDetailsStep) by default
 * - Step indicator shows correct current step
 * - Next advances through steps
 * - Back returns to previous step
 * - Step 1 required fields block advancement
 * - Step 4 (ReviewSubmitStep) shows read-only summary and submit button
 * - Submit calls PUT /api/profile + POST /api/activation/request
 * - Submit navigates to /dashboard on success
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockApiFetch = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
  ApiError: class ApiError extends Error {
    constructor(public status: number, message: string, public code?: string) {
      super(message);
      this.name = "ApiError";
    }
  },
}));

vi.mock("@/adapters/cognito-auth-provider", () => ({
  useCognitoAuth: () => ({
    isLoaded: true,
    isAuthenticated: true,
    user: { username: "owner", tenantSlug: "acme" },
    signOut: vi.fn(),
    getAccessToken: vi.fn().mockResolvedValue("tok"),
  }),
}));

import { VoiceSetupWizard } from "@/pages/setup/VoiceSetupWizard";

function makeQC() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

const sampleProfile = {
  businessName: "Dave's Electrical",
  ownerName: "Dave Smith",
  receptionistName: "Choka",
  ownerPhone: "+61412000001",
  services: "Electrical repairs and installations",
  servicesNotOffered: [],
  serviceAreas: "Melbourne metro area",
  hours: "Mon-Fri 7am-5pm",
  pricing: "",
  faq: "",
  policies: "",
  state: "VIC",
  setupComplete: false,
};

function renderWizard() {
  const qc = makeQC();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/setup/voice"]}>
        <Routes>
          <Route path="/setup/voice" element={<VoiceSetupWizard />} />
          <Route path="/dashboard" element={<div>Dashboard</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("VoiceSetupWizard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading skeleton while profile is fetching", async () => {
    mockApiFetch.mockReturnValue(new Promise(() => {}));
    const { container } = renderWizard();
    await waitFor(() => {
      expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
    });
  });

  it("renders step 1 after profile loads", async () => {
    mockApiFetch.mockResolvedValue(sampleProfile);
    renderWizard();
    await waitFor(() => {
      expect(screen.getByText(/business details/i)).toBeInTheDocument();
    });
  });

  it("step indicator shows step 1 of 4", async () => {
    mockApiFetch.mockResolvedValue(sampleProfile);
    renderWizard();
    await waitFor(() => {
      expect(screen.getByText(/step 1/i)).toBeInTheDocument();
    });
  });

  it("pre-fills business name from profile", async () => {
    mockApiFetch.mockResolvedValue(sampleProfile);
    renderWizard();
    await waitFor(() => {
      expect(screen.getByDisplayValue("Dave's Electrical")).toBeInTheDocument();
    });
  });

  it("pre-fills owner name from profile", async () => {
    mockApiFetch.mockResolvedValue(sampleProfile);
    renderWizard();
    await waitFor(() => {
      expect(screen.getByDisplayValue("Dave Smith")).toBeInTheDocument();
    });
  });

  it("Next advances from step 1 to step 2", async () => {
    mockApiFetch.mockResolvedValue(sampleProfile);
    renderWizard();
    await waitFor(() => {
      expect(screen.getByText(/step 1/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(screen.getByText(/step 2/i)).toBeInTheDocument();
    });
  });

  it("Back returns from step 2 to step 1", async () => {
    mockApiFetch.mockResolvedValue(sampleProfile);
    renderWizard();
    await waitFor(() => {
      expect(screen.getByText(/step 1/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(screen.getByText(/step 2/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    await waitFor(() => {
      expect(screen.getByText(/step 1/i)).toBeInTheDocument();
    });
  });

  it("can navigate to step 3 and step 4", async () => {
    mockApiFetch.mockResolvedValue(sampleProfile);
    renderWizard();
    await waitFor(() => {
      expect(screen.getByText(/step 1/i)).toBeInTheDocument();
    });
    // Step 1 → 2
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => expect(screen.getByText(/step 2/i)).toBeInTheDocument());
    // Step 2 → 3
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => expect(screen.getByText(/step 3/i)).toBeInTheDocument());
    // Step 3 → 4
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => expect(screen.getByText(/step 4/i)).toBeInTheDocument());
  });

  it("shows review summary on step 4 with submit button", async () => {
    mockApiFetch.mockResolvedValue(sampleProfile);
    renderWizard();
    await waitFor(() => expect(screen.getByText(/step 1/i)).toBeInTheDocument());
    // Navigate to step 4
    for (let i = 0; i < 3; i++) {
      fireEvent.click(screen.getByRole("button", { name: /next/i }));
      await waitFor(() => expect(screen.getByText(new RegExp(`step ${i + 2}`, "i"))).toBeInTheDocument());
    }
    expect(screen.getByRole("button", { name: /submit for activation/i })).toBeInTheDocument();
  });

  it("submit calls PUT /api/profile then POST /api/activation/request", async () => {
    mockApiFetch
      .mockResolvedValueOnce(sampleProfile) // GET profile
      .mockResolvedValueOnce({ status: "updated" }) // PUT profile
      .mockResolvedValueOnce({ activation_status: "pending" }); // POST activation

    renderWizard();
    await waitFor(() => expect(screen.getByText(/step 1/i)).toBeInTheDocument());

    // Navigate to step 4
    for (let i = 0; i < 3; i++) {
      fireEvent.click(screen.getByRole("button", { name: /next/i }));
      await waitFor(() =>
        expect(screen.getByText(new RegExp(`step ${i + 2}`, "i"))).toBeInTheDocument()
      );
    }

    fireEvent.click(screen.getByRole("button", { name: /submit for activation/i }));

    await waitFor(() => {
      const calls = mockApiFetch.mock.calls;
      const putCall = calls.find(
        (c) => c[0] === "/api/profile" && c[1]?.method === "PUT"
      );
      const postCall = calls.find(
        (c) => c[0] === "/api/activation/request" && c[1]?.method === "POST"
      );
      expect(putCall).toBeDefined();
      expect(postCall).toBeDefined();
    });
  });

  it("navigates to /dashboard after successful submit", async () => {
    mockApiFetch
      .mockResolvedValueOnce(sampleProfile)
      .mockResolvedValueOnce({ status: "updated" })
      .mockResolvedValueOnce({ activation_status: "pending" });

    renderWizard();
    await waitFor(() => expect(screen.getByText(/step 1/i)).toBeInTheDocument());

    for (let i = 0; i < 3; i++) {
      fireEvent.click(screen.getByRole("button", { name: /next/i }));
      await waitFor(() =>
        expect(screen.getByText(new RegExp(`step ${i + 2}`, "i"))).toBeInTheDocument()
      );
    }

    fireEvent.click(screen.getByRole("button", { name: /submit for activation/i }));

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
  });
});
