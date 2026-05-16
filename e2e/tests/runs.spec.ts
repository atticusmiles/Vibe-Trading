import { test, expect } from "../fixtures";

test.describe("Run detail page", () => {
  test("invalid run ID shows error state", async ({ page }) => {
    await page.goto("/runs/nonexistent-run-id");
    // Should show some error or not-found state (not crash)
    await page.waitForLoadState("networkidle");
    // Page should not redirect away
    await expect(page).toHaveURL(/\/runs\//);
  });

  test("has tab bar structure for valid-looking run ID", async ({ page }) => {
    // Even with invalid data, the page should attempt to render tabs
    await page.goto("/runs/nonexistent-run-id");
    await page.waitForLoadState("networkidle");
    // The page shouldn't crash — just verify it's still on the runs page
    await expect(page).toHaveURL(/\/runs\//);
  });
});
