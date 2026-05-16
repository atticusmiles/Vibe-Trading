import { test, expect } from "../fixtures";

test.describe("Settings page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");
  });

  test("shows Preferences tab by default", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Investment Style" })).toBeVisible({ timeout: 15000 });
  });

  test("switches to System tab", async ({ page }) => {
    await page.getByRole("button", { name: "System Settings" }).click();
    await expect(page.getByRole("heading", { name: "Scheduler" })).toBeVisible({ timeout: 10000 });
  });

  test("switches to Security tab", async ({ page }) => {
    await page.getByRole("button", { name: "Security" }).click();
    await expect(page.getByRole("heading", { name: "Change Password" })).toBeVisible({ timeout: 10000 });
  });

  test.describe("Preferences tab", () => {
    test("has all form elements", async ({ page }) => {
      await expect(page.getByRole("heading", { name: "Investment Style" })).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole("heading", { name: "Markets & Industries" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Capital & Strategy" })).toBeVisible();
      await expect(page.getByText("Style").first()).toBeVisible();
      await expect(page.getByText("Risk Appetite").first()).toBeVisible();
      await expect(page.getByText("Focus Markets").first()).toBeVisible();
      await expect(page.getByText("Focus Industries").first()).toBeVisible();
      await expect(page.getByText("Holding Period").first()).toBeVisible();
      await expect(page.getByText("Capital Scale").first()).toBeVisible();
      await expect(page.getByText("Stock Investment Total").first()).toBeVisible();
      await expect(page.getByText("Avoid Targets").first()).toBeVisible();
      await expect(page.getByText("Custom Notes").first()).toBeVisible();
    });

    test("save and reset buttons exist", async ({ page }) => {
      const saveBtn = page.getByRole("button", { name: "Save" });
      await expect(saveBtn).toBeVisible({ timeout: 15000 });
      const resetBtn = page.getByRole("button", { name: "Reset" });
      await expect(resetBtn).toBeVisible();
    });

    test("modify and save shows toast", async ({ page }) => {
      const select = page.locator("select").first();
      await expect(select).toBeVisible({ timeout: 15000 });
      await select.selectOption({ index: 1 });
      await page.getByRole("button", { name: "Save" }).first().click();
      await expect(page.getByText("Preferences saved")).toBeVisible({ timeout: 10000 });
    });

    test("reset reverts changes", async ({ page }) => {
      const select = page.locator("select").first();
      await expect(select).toBeVisible({ timeout: 15000 });
      const initialValue = await select.inputValue();
      await select.selectOption({ index: 1 });
      expect(await select.inputValue()).not.toBe(initialValue);

      await page.getByRole("button", { name: "Reset" }).first().click();
      expect(await select.inputValue()).toBe(initialValue);
    });
  });

  test.describe("System tab", () => {
    test.beforeEach(async ({ page }) => {
      await page.getByRole("button", { name: "System Settings" }).click();
      await page.waitForLoadState("networkidle");
    });

    test("has scheduler inputs", async ({ page }) => {
      await expect(page.getByText("News Archive Time").first()).toBeVisible({ timeout: 10000 });
      await expect(page.getByText("Sentinel Interval").first()).toBeVisible();
    });

    test("has proposal limits", async ({ page }) => {
      await expect(page.getByRole("heading", { name: "Proposal Limits" })).toBeVisible({ timeout: 10000 });
      await expect(page.getByText("Trend").first()).toBeVisible();
      await expect(page.getByText("Industry").first()).toBeVisible();
      await expect(page.getByText("Stock").first()).toBeVisible();
    });
  });

  test.describe("Security tab", () => {
    test.beforeEach(async ({ page }) => {
      await page.getByRole("button", { name: "Security" }).click();
      await page.waitForLoadState("networkidle");
    });

    test("has password fields", async ({ page }) => {
      await expect(page.getByText("Current Password").first()).toBeVisible({ timeout: 10000 });
      await expect(page.getByText("New Password").first()).toBeVisible();
      await expect(page.getByText("Confirm New Password").first()).toBeVisible();
    });

    test("shows mismatch warning", async ({ page }) => {
      const inputs = page.locator('input[type="password"]');
      await expect(inputs.nth(1)).toBeVisible({ timeout: 10000 });
      await inputs.nth(1).fill("NewPass123!");
      await inputs.nth(2).fill("Different456!");
      await expect(page.getByText("Passwords do not match")).toBeVisible();
    });

    test("save with empty fields shows error", async ({ page }) => {
      await expect(page.getByText("Current Password").first()).toBeVisible({ timeout: 10000 });
      const saveBtns = page.getByRole("button", { name: "Save" });
      await saveBtns.first().click();
      await expect(page.getByText(/fill in all fields/i)).toBeVisible({ timeout: 10000 });
    });
  });
});
