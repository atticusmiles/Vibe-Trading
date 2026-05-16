import { test as setup, expect } from "@playwright/test";
import fs from "fs";
import path from "path";

const STORAGE_KEY = "vibe_trading_api_auth_key";
const timestamp = Date.now();
const username = `e2e_${timestamp}`;
const password = "E2eTest123!";

setup("authenticate", async ({ request }) => {
  // Register via API (using relative path — proxied through baseURL)
  const regRes = await request.post("/auth/register", {
    data: { username, password },
  });
  expect(regRes.status()).toBe(201);

  // Login
  const loginRes = await request.post("/auth/login", {
    data: { username, password },
  });
  expect(loginRes.status()).toBe(200);
  const { access_token } = await loginRes.json();

  // Save storageState for authenticated tests
  const baseURL = process.env.E2E_BASE_URL || "http://localhost:5899";
  const origin = new URL(baseURL).origin;
  const state = {
    origins: [
      {
        origin,
        localStorage: [],
        sessionStorage: [{ name: STORAGE_KEY, value: access_token }],
      },
    ],
  };

  const dir = path.join(__dirname, "..", "storage-state");
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "authenticated.json"), JSON.stringify(state, null, 2));

  // Save credentials for tests that need them
  fs.writeFileSync(
    path.join(dir, "credentials.json"),
    JSON.stringify({ username, password, token: access_token }),
  );
});
