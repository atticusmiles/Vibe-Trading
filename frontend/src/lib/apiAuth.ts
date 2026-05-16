const STORAGE_KEY = "vibe_trading_api_auth_key";

export function getApiAuthKey(): string {
  return window.localStorage.getItem(STORAGE_KEY) || "";
}

export function setApiAuthKey(value: string): void {
  const trimmed = value.trim();
  if (trimmed) {
    window.localStorage.setItem(STORAGE_KEY, trimmed);
  } else {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}

export function clearApiAuthKey(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}

export function isLoggedIn(): boolean {
  return !!getApiAuthKey();
}

export function authHeaders(): Record<string, string> {
  const key = getApiAuthKey();
  return key ? { Authorization: `Bearer ${key}` } : {};
}

export function withAuthQuery(url: string): string {
  const key = getApiAuthKey();
  if (!key) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(key)}`;
}
