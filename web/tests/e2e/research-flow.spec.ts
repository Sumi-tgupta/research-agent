import { test, expect } from "@playwright/test";
import { mockBackend } from "./mock-backend";

const QUERY = "Compare small modular reactors to conventional nuclear";
const REPORT =
  "## Executive summary\n\nSMRs trade a higher per-MWh cost for improved passive safety [1]. Deployment timelines remain the key uncertainty.";

test.describe("research flow", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackend(page, { query: QUERY, report: REPORT });
  });

  test("runs a query and renders the report", async ({ page }) => {
    await page.goto("/");

    await page.getByPlaceholder(/ask a research question/i).fill(QUERY);
    await page.getByRole("button", { name: /start research/i }).click();

    // The tracker flips to "Completed" once the mocked stream ends.
    await expect(page.getByText(/completed/i)).toBeVisible();

    // The report markdown is rendered in the main column.
    await expect(page.getByText(/executive summary/i)).toBeVisible();
    await expect(page.getByText(/improved passive safety/i)).toBeVisible();
  });

  test("exposes the result tabs and lets you switch to Sources", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByPlaceholder(/ask a research question/i).fill(QUERY);
    await page.getByRole("button", { name: /start research/i }).click();
    await expect(page.getByText(/completed/i)).toBeVisible();

    const sourcesTab = page.getByRole("tab", { name: /sources/i });
    await sourcesTab.click();
    await expect(sourcesTab).toHaveAttribute("aria-selected", "true");
  });
});
