import "@testing-library/jest-dom";
import { toHaveNoViolations } from "vitest-axe/matchers";
import { expect } from "vitest";

// Extend vitest expect with axe toHaveNoViolations
expect.extend({ toHaveNoViolations });
