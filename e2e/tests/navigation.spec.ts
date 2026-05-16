import { test, expect } from "../fixtures";

test.describe("Navigation and layout", () => {
  test("sidebar shows 4 nav links", async ({ page }) => {
    await page.goto("/");
    const aside = page.locator("aside");
    await expect(aside).toBeVisible({ timeout: 10000 });
    const navLinks = aside.locator("nav a");
    await expect(navLinks).toHaveCount(4, { timeout: 10000 });
  });

  test("navigates between pages", async ({ page }) => {
    await page.goto("/");
    const aside = page.locator("aside");
    await expect(aside).toBeVisible({ timeout: 10000 });

    // Navigate to Agent
    await aside.locator("nav a[href='/agent']").click();
    await expect(page).toHaveURL("/agent", { timeout: 10000 });

    // Navigate to Tools
    await aside.locator("nav a[href='/tools']").click();
    await expect(page).toHaveURL("/tools", { timeout: 10000 });

    // Navigate to Settings
    await aside.locator("nav a[href='/settings']").click();
    await expect(page).toHaveURL("/settings", { timeout: 10000 });

    // Navigate to Home
    await aside.locator("nav a[href='/']").click();
    await expect(page).toHaveURL("/", { timeout: 10000 });
  });

  test("sidebar collapse and expand", async ({ page }) => {
    await page.goto("/");
    const aside = page.locator("aside");

    // Wait for sidebar to be fully loaded
    await expect(aside.getByText("Vibe-Trading")).toBeVisible({ timeout: 10000 });

    // Collapse — click the collapse button (ChevronsLeft icon)
    await page.locator("aside button[title='Collapse']").click();
    await expect(aside.getByText("Vibe-Trading")).not.toBeVisible({ timeout: 5000 });

    // Expand — click the expand button (ChevronsRight icon)
    await page.locator("aside button[title='Expand']").click();
    await expect(aside.getByText("Vibe-Trading")).toBeVisible({ timeout: 5000 });
  });

  test("dark mode toggle", async ({ page }) => {
    await page.goto("/");
    // Find the dark/light toggle button by its text content
    const toggleBtn = page.locator("aside").getByRole("button", { name: /dark|light/i }).first();
    await expect(toggleBtn).toBeVisible({ timeout: 10000 });
    await toggleBtn.click();
    // Verify dark class on html
    const htmlClass = await page.locator("html").getAttribute("class");
    expect(htmlClass).toMatch(/dark/);
  });

  test("logout redirects to /login", async ({ page }) => {
    await page.goto("/");
    // Find logout button by title
    const logoutBtn = page.locator("aside button[title='Logout']");
    await expect(logoutBtn).toBeVisible({ timeout: 10000 });
    await logoutBtn.click();
    await expect(page).toHaveURL("/login", { timeout: 10000 });
  });
});
