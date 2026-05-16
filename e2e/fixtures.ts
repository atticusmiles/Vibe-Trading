import { test as base } from "@playwright/test";
import fs from "fs";
import path from "path";

const STORAGE_KEY = "vibe_trading_api_auth_key";

export const test = base.extend({
  page: async ({ page }, use) => {
    const credPath = path.join(__dirname, "storage-state", "credentials.json");
    if (fs.existsSync(credPath)) {
      const creds = JSON.parse(fs.readFileSync(credPath, "utf-8"));
      await page.addInitScript((token) => {
        window.sessionStorage.setItem("vibe_trading_api_auth_key", token);
      }, creds.token);
    }
    await use(page);
  },
});

export { expect } from "@playwright/test";
