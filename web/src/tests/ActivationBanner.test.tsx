/**
 * Tests for dashboard-10: ActivationBanner component.
 *
 * Now imports from @chokaau/ui — local duplicate deleted.
 *
 * TDD: Tests cover:
 * - Shows banner when activation_status is "pending"
 * - Does not show banner when activation_status is "none"
 * - Does not show banner when activation_status is "active"
 * - Dismiss button hides the banner
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ActivationBanner } from "@chokaau/ui";

describe("ActivationBanner", () => {
  it("shows banner when status is pending", () => {
    render(<ActivationBanner status="pending" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/being reviewed/i)).toBeInTheDocument();
  });

  it("does not show banner when status is none", () => {
    render(<ActivationBanner status="none" />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not show banner when status is active", () => {
    render(<ActivationBanner status="active" />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("dismiss button hides the banner", () => {
    render(<ActivationBanner status="pending" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
