import { test, expect } from "../fixtures";

test.describe("Compare page", () => {
  test("shows two dropdown selectors", async ({ page }) => {
    await page.goto("/compare");
    // Wait for the page to fully load (API call for runs)
    const selects = page.locator("select");
    await expect(selects).toHaveCount(2, { timeout: 15000 });
  });

  test("shows empty state when no runs selected", async ({ page }) => {
    await page.goto("/compare");
    // Metrics table should not exist when no data
    await page.waitForLoadState("networkidle");
    const table = page.locator("table");
    // Table only shows when there's data; with no runs, empty state shows
    await expect(table).not.toBeVisible();
  });
});
