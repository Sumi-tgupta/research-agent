import { test, expect } from "@playwright/test";

test.describe("library page", () => {
  test("renders the header and a sign-in gate", async ({ page }) => {
    await page.goto("/library");

    await expect(
      page.getByRole("heading", { name: /saved research/i })
    ).toBeVisible();

    // Anonymous mode (no Supabase env) shows the "not configured" notice; a
    // configured-but-signed-out deployment shows the "sign in" prompt. Accept
    // either so the test is robust to how the runner is configured.
    await expect(
      page.getByText(
        /sign-in isn.t configured|sign in to view your library/i
      )
    ).toBeVisible();
  });
});
