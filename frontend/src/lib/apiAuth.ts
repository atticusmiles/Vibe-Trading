const STORAGE_KEY = "vibe_trading_api_auth_key";

export function getApiAuthKey(): string {
  return window.sessionStorage.getItem(STORAGE_KEY) || "";
}

export function setApiAuthKey(value: string): void {
  const trimmed = value.trim();
  if (trimmed) {
    window.sessionStorage.setItem(STORAGE_KEY, trimmed);
    // Broadcast to other tabs via localStorage event
    window.localStorage.setItem(STORAGE_KEY + "_sync", trimmed);
    window.localStorage.removeItem(STORAGE_KEY + "_sync");
  } else {
    window.sessionStorage.removeItem(STORAGE_KEY);
  }
}

export function clearApiAuthKey(): void {
  window.sessionStorage.removeItem(STORAGE_KEY);
  // Broadcast logout to other tabs
  window.localStorage.setItem(STORAGE_KEY + "_sync", "");
  window.localStorage.removeItem(STORAGE_KEY + "_sync");
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

// Listen for auth changes from other tabs (localStorage storage event
// fires in all OTHER tabs when an item is set/removed).
if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === STORAGE_KEY + "_sync") {
      const newValue = e.newValue;
      if (newValue) {
        window.sessionStorage.setItem(STORAGE_KEY, newValue);
      } else {
        window.sessionStorage.removeItem(STORAGE_KEY);
        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
      }
    }
  });
}
