/**
 * Shared email validation utilities.
 *
 * Extracted to eliminate duplication between SignUpPage and SignInPage (GEN-MAINT-02).
 */

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Validates an email value.
 * Returns an error string if invalid, or empty string if valid.
 */
export function validateEmail(value: string): string {
  if (!value.trim()) return "Email is required";
  if (!EMAIL_RE.test(value)) return "Invalid email address";
  return "";
}
