import { test, expect } from "../fixtures";

test.describe("Agent page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/agent");
  });

  test("shows welcome screen when no messages", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Vibe-Trading" })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Multi-Market Backtest")).toBeVisible();
  });

  test("has textarea input", async ({ page }) => {
    const textarea = page.locator("textarea");
    await expect(textarea).toBeVisible({ timeout: 15000 });
  });

  test("send button disabled when input empty", async ({ page }) => {
    const submitBtn = page.locator('button[type="submit"]');
    await expect(submitBtn).toBeVisible({ timeout: 15000 });
    await expect(submitBtn).toBeDisabled();
  });

  test("send button enabled after typing", async ({ page }) => {
    const textarea = page.locator("textarea");
    await expect(textarea).toBeVisible({ timeout: 15000 });
    await textarea.fill("test query");
    const submitBtn = page.locator('button[type="submit"]');
    await expect(submitBtn).toBeEnabled();
  });

  test("+ button opens options menu", async ({ page }) => {
    // The "+" button has a circle shape
    const plusBtn = page.locator('button:has(svg.lucide-plus)').first();
    await expect(plusBtn).toBeVisible({ timeout: 15000 });
    await plusBtn.click();
    await expect(page.getByText("Upload PDF document")).toBeVisible();
    await expect(page.getByText("Agent Swarm")).toBeVisible();
  });

  test("swarm mode badge appears and removable", async ({ page }) => {
    // Open menu
    const plusBtn = page.locator('button:has(svg.lucide-plus)').first();
    await expect(plusBtn).toBeVisible({ timeout: 15000 });
    await plusBtn.click();
    await page.getByText("Agent Swarm").click();

    // Badge visible
    const badge = page.locator("span").filter({ hasText: "Agent Swarm" }).first();
    await expect(badge).toBeVisible();

    // Close badge
    await badge.locator("button").click();
    await expect(badge).not.toBeVisible();
  });

  test("export button not visible when no messages", async ({ page }) => {
    // Export button only appears when messages exist
    const exportBtn = page.locator('button[title="Export chat"]');
    await expect(exportBtn).not.toBeVisible();
  });
});
