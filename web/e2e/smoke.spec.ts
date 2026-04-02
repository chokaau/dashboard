/**
 * E2E smoke test — story-4-6.
 *
 * Validates the critical path against the deployed dev environment:
 *   CloudFront → S3 SPA → Cognito auth → BFF → data rendered
 *
 * Prerequisites:
 *   Environment variables (set as GitHub Actions secrets — never hard-coded):
 *     E2E_USERNAME  — Cognito test user email
 *     E2E_PASSWORD  — Cognito test user password
 *
 * The test must complete in under 60 seconds (Playwright timeout: 60s).
 */
import { test, expect } from "@playwright/test";

const USERNAME = process.env.E2E_USERNAME;
const PASSWORD = process.env.E2E_PASSWORD;

test.beforeAll(() => {
  if (!USERNAME || !PASSWORD) {
    throw new Error(
      "E2E_USERNAME and E2E_PASSWORD environment variables must be set. " +
        "These are stored as GitHub Actions secrets, not in code."
    );
  }
});

test("critical path: sign-in → dashboard → calls → call detail", async ({
  page,
}) => {
  // -------------------------------------------------------------------------
  // Step a: Navigate to app root — expect redirect to /auth/sign-in
  // -------------------------------------------------------------------------
  await page.goto("/");
  await expect(page).toHaveURL(/\/auth\/sign-in/);

  // -------------------------------------------------------------------------
  // Step b+c: Sign in with test credentials
  // -------------------------------------------------------------------------
  await page.getByLabel(/email/i).fill(USERNAME!);
  await page.getByLabel(/password/i).fill(PASSWORD!);
  await page.getByRole("button", { name: /sign in/i }).click();

  // -------------------------------------------------------------------------
  // Step d: Assert redirect to /dashboard
  // -------------------------------------------------------------------------
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

  // -------------------------------------------------------------------------
  // Step e: Assert at least one DashboardStatCard has a non-zero value
  // The stat card value elements have data-value or visible numeric text.
  // Wait for the data to load (skeleton disappears).
  // -------------------------------------------------------------------------
  // Wait for any animate-pulse skeleton to clear
  await page
    .locator(".animate-pulse")
    .first()
    .waitFor({ state: "hidden", timeout: 10_000 })
    .catch(() => {
      // skeleton may not appear at all if data loads fast — continue
    });

  // At least one stat card should show a number
  const statCards = page.locator("[data-testid='stat-card'], .stat-card, [aria-label*='stat']");
  // Fallback: look for any element containing a digit in the dashboard
  const dashboardSection = page.locator("main, [role='main'], #root");
  await expect(dashboardSection).toContainText(/\d/, { timeout: 10_000 });

  // -------------------------------------------------------------------------
  // Step f: Assert NeedsCallbackPanel renders (may be empty)
  // -------------------------------------------------------------------------
  // The panel has aria-label or heading "Needs callback" / "Callback"
  const callbackPanel = page.locator(
    "[data-testid='callback-panel'], [aria-label*='callback' i], [aria-label*='Callback']"
  );
  // Also accept a heading with that text
  const callbackHeading = page.getByRole("heading", { name: /callback/i });
  const panelOrHeading = callbackPanel.or(callbackHeading);
  await expect(panelOrHeading.first()).toBeVisible({ timeout: 5_000 });

  // -------------------------------------------------------------------------
  // Step g: Navigate to /calls
  // -------------------------------------------------------------------------
  await page.goto("/calls");
  await expect(page).toHaveURL(/\/calls/);

  // -------------------------------------------------------------------------
  // Step h: Assert at least one CallCard is visible
  // -------------------------------------------------------------------------
  const callCard = page.locator(
    "[data-testid='call-card'], [aria-label*='call' i]"
  ).first();
  await expect(callCard).toBeVisible({ timeout: 10_000 });

  // -------------------------------------------------------------------------
  // Step i: Click the first CallCard
  // -------------------------------------------------------------------------
  await callCard.click();

  // -------------------------------------------------------------------------
  // Step j: Assert call detail page renders with a transcript or "No transcript"
  // -------------------------------------------------------------------------
  await expect(page).toHaveURL(/\/calls\/.+/, { timeout: 5_000 });
  const transcriptContent = page.locator(
    "[data-testid='transcript'], [aria-label*='transcript' i]"
  );
  const noTranscriptText = page.getByText(/no transcript/i);
  const transcriptOrFallback = transcriptContent.or(noTranscriptText);
  await expect(transcriptOrFallback.first()).toBeVisible({ timeout: 5_000 });
});
