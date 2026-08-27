import { test, expect } from "@playwright/test";
import { mockBackend } from "./mock-backend";

test.describe("landing page", () => {
  test("presents the hero and pipeline overview", async ({ page }) => {
    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: /answers you can trace/i })
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /nine agents, one traceable answer/i })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /start research/i })
    ).toBeVisible();
  });

  test("launches a run from an example chip", async ({ page }) => {
    await mockBackend(page, {
      query: "example",
      report: "## Findings\n\nExample synthesis with a citation [1].",
    });

    await page.goto("/");
    await page
      .getByRole("button", { name: /small modular reactors compare/i })
      .click();

    await expect(page.getByText(/completed/i)).toBeVisible();
    await expect(page.getByText(/findings/i)).toBeVisible();
  });
});
