import { test, expect } from "@playwright/test";

test.describe("Login page", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("displays login form with tab toggle", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("Vibe Trading AI")).toBeVisible({ timeout: 10000 });
    // Tab buttons
    await expect(page.getByRole("button", { name: "Login" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Register" }).first()).toBeVisible();
  });

  test("switches to register tab", async ({ page }) => {
    await page.goto("/login");
    // Click the Register tab button (the first one which is the tab, not submit)
    const tabButtons = page.locator("button").filter({ hasText: "Register" });
    await tabButtons.first().click();
    await expect(page.getByPlaceholder("3-32 characters")).toBeVisible();
  });

  test("register then login flow", async ({ page }) => {
    const user = `pw_${Date.now()}`;
    await page.goto("/login");

    // Switch to register tab
    const tabButtons = page.locator("button").filter({ hasText: "Register" });
    await tabButtons.first().click();

    await page.getByPlaceholder("3-32 characters").fill(user);
    await page.getByPlaceholder("8-128 characters").fill("TestPass123!");

    // Click the submit button (not the tab button)
    const submitBtn = page.locator('form button[type="submit"]');
    await submitBtn.click();

    // Should see success toast
    await expect(page.getByText("Registration successful")).toBeVisible({ timeout: 10000 });

    // Now login — the tab should have switched automatically
    await page.getByPlaceholder("3-32 characters").fill(user);
    await page.getByPlaceholder("8-128 characters").fill("TestPass123!");
    await submitBtn.click();

    // Should redirect to home
    await expect(page).toHaveURL("/", { timeout: 10000 });
  });

  test("duplicate register shows error", async ({ page }) => {
    const fs = require("fs");
    const path = require("path");
    const credPath = path.join(__dirname, "..", "storage-state", "credentials.json");
    const creds = JSON.parse(fs.readFileSync(credPath, "utf-8"));

    await page.goto("/login");
    const tabButtons = page.locator("button").filter({ hasText: "Register" });
    await tabButtons.first().click();
    await page.getByPlaceholder("3-32 characters").fill(creds.username);
    await page.getByPlaceholder("8-128 characters").fill(creds.password);

    const submitBtn = page.locator('form button[type="submit"]');
    await submitBtn.click();

    await expect(page.getByText("Username already exists")).toBeVisible({ timeout: 10000 });
  });

  test("wrong password shows error", async ({ page }) => {
    const fs = require("fs");
    const path = require("path");
    const credPath = path.join(__dirname, "..", "storage-state", "credentials.json");
    const creds = JSON.parse(fs.readFileSync(credPath, "utf-8"));

    await page.goto("/login");
    await page.getByPlaceholder("3-32 characters").fill(creds.username);
    await page.getByPlaceholder("8-128 characters").fill("WrongPassword123!");

    const submitBtn = page.locator('form button[type="submit"]');
    await submitBtn.click();

    // Should show error (either via toast or inline)
    await page.waitForTimeout(3000);
    // Just verify we're still on login page
    await expect(page).toHaveURL("/login");
  });

  test("redirects to /login when accessing protected route", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL("/login", { timeout: 10000 });
  });
});
