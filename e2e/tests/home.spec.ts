import { test, expect } from "../fixtures";

test.describe("Home page", () => {
  test("displays hero section and features", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    // 4 feature cards
    const cards = page.locator("div.border.rounded-lg");
    await expect(cards).toHaveCount(4, { timeout: 15000 });
  });

  test("Start Research link navigates to /agent", async ({ page }) => {
    await page.goto("/");
    const link = page.getByRole("link", { name: /start research/i });
    await expect(link).toBeVisible({ timeout: 10000 });
    await link.click();
    await expect(page).toHaveURL("/agent", { timeout: 10000 });
  });
});
