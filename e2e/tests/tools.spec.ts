import { test, expect } from "../fixtures";

test.describe("Tools page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/tools");
    await page.waitForLoadState("networkidle");
  });

  test("shows Correlation Matrix tab", async ({ page }) => {
    await expect(page.getByText("Correlation Matrix")).toBeVisible({ timeout: 15000 });
  });

  test("has asset codes input with default value", async ({ page }) => {
    const input = page.locator("input[type='text']");
    await expect(input).toBeVisible({ timeout: 15000 });
    const value = await input.inputValue();
    expect(value).toContain("BTC-USDT");
  });

  test("window selector buttons work", async ({ page }) => {
    const btn30 = page.getByText("30d", { exact: true });
    const btn365 = page.getByText("365d", { exact: true });

    await expect(btn30).toBeVisible({ timeout: 15000 });
    await btn365.click();
    await expect(btn365).toHaveClass(/bg-primary/);
  });

  test("method selector buttons work", async ({ page }) => {
    const pearson = page.getByText("pearson", { exact: true });
    const spearman = page.getByText("spearman", { exact: true });

    await expect(pearson).toBeVisible({ timeout: 15000 });
    await spearman.click();
    await expect(spearman).toHaveClass(/bg-primary/);
  });

  test("compute button is present and clickable", async ({ page }) => {
    const btn = page.getByRole("button", { name: "Compute" });
    await expect(btn).toBeVisible({ timeout: 15000 });
    await btn.click();
    // Just verify no crash — loading state or error/success is acceptable
    await page.waitForTimeout(2000);
  });
});
