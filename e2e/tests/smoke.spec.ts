import { test, expect } from "@playwright/test";
import fs from "fs";
import path from "path";

let token: string;

test.beforeAll(() => {
  const credPath = path.join(__dirname, "..", "storage-state", "credentials.json");
  const creds = JSON.parse(fs.readFileSync(credPath, "utf-8"));
  token = creds.token;
});

const authHeader = () => ({ Authorization: `Bearer ${token}` });

test("GET /health returns 200", async ({ request }) => {
  const res = await request.get("/health");
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.status).toBe("healthy");
});

test("GET /api returns 200", async ({ request }) => {
  const res = await request.get("/api");
  expect(res.status()).toBe(200);
});

test("POST /auth/register returns 201 for new user", async ({ request }) => {
  const res = await request.post("/auth/register", {
    data: { username: `smoke_${Date.now()}`, password: "SmokeTest123!" },
  });
  expect(res.status()).toBe(201);
  const body = await res.json();
  expect(body).toHaveProperty("id");
  expect(body).toHaveProperty("username");
});

test("POST /auth/login returns 200 with token", async ({ request }) => {
  const credPath = path.join(__dirname, "..", "storage-state", "credentials.json");
  const creds = JSON.parse(fs.readFileSync(credPath, "utf-8"));
  const res = await request.post("/auth/login", {
    data: { username: creds.username, password: creds.password },
  });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.access_token).toBeTruthy();
  expect(body.token_type).toBe("bearer");
});

test("GET /auth/me returns user info", async ({ request }) => {
  const res = await request.get("/auth/me", { headers: authHeader() });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body).toHaveProperty("id");
  expect(body).toHaveProperty("username");
});

test("GET /sessions returns 200", async ({ request }) => {
  const res = await request.get("/sessions", { headers: authHeader() });
  expect(res.status()).toBe(200);
});

test("GET /skills returns 200", async ({ request }) => {
  const res = await request.get("/skills", { headers: authHeader() });
  expect(res.status()).toBe(200);
});

test("GET /runs returns 200", async ({ request }) => {
  const res = await request.get("/runs", { headers: authHeader() });
  expect(res.status()).toBe(200);
});

test("GET /sessions without auth returns 401", async ({ request }) => {
  const res = await request.get("/sessions");
  expect(res.status()).toBe(401);
});
