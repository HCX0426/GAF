/**
 * Token & Multi-Account Storage Utilities
 *
 * Access Token in memory + sessionStorage backup (survives page refresh, cleared on tab close).
 * Refresh Token in localStorage (remember_me=true) or sessionStorage (remember_me=false).
 * Multi-account credentials stored in localStorage for quick switching.
 *
 * P1-5/P1-6: access token persisted to sessionStorage to reduce refresh calls on page reload.
 * P1-4: cross-tab sync via 'storage' event listener.
 */

let inMemoryAccessToken: string | null = null;

const ACCESS_TOKEN_KEY = 'access_token'; // sessionStorage only
const REFRESH_TOKEN_KEY = 'refresh_token'; // localStorage or sessionStorage based on remember_me
const REMEMBER_ME_KEY = 'remember_me';
const SAVED_ACCOUNTS_KEY = 'gaf_saved_accounts';

/** Saved account credential for multi-account switching */
export interface SavedAccount {
  /** Account username */
  username: string;
  /** Refresh token for this account */
  refreshToken: string;
  /** ISO timestamp when this account was saved */
  savedAt: string;
}

/** Get the Access Token — checks memory first, then sessionStorage (page refresh recovery) */
export function getAccessToken(): string | null {
  if (inMemoryAccessToken) return inMemoryAccessToken;
  try {
    const stored = sessionStorage.getItem(ACCESS_TOKEN_KEY);
    if (stored) {
      inMemoryAccessToken = stored;
      return stored;
    }
  } catch {
    // sessionStorage unavailable
  }
  return null;
}

/**
 * M22: Build authenticated request headers for raw fetch() calls.
 * Reads the in-memory access token and adds `Authorization: Bearer <token>`
 * if present. Merges with optional base headers.
 *
 * NOTE: For axios requests via `@/api/client`, the request interceptor
 * already injects the Authorization header — do NOT use this helper there.
 * Use this only for raw fetch() calls that bypass the axios client.
 *
 * @param base - Optional base headers to merge (e.g. {'Content-Type': 'application/json'})
 * @returns Headers object with Authorization if token exists
 */
export function buildAuthHeaders(base: Record<string, string> = {}): Record<string, string> {
  const token = getAccessToken();
  const headers: Record<string, string> = { ...base };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

/** Set the Access Token — writes to both memory and sessionStorage (survives page refresh) */
export function setAccessToken(token: string | null): void {
  inMemoryAccessToken = token;
  try {
    if (token) {
      sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
    } else {
      sessionStorage.removeItem(ACCESS_TOKEN_KEY);
    }
  } catch {
    // sessionStorage unavailable
  }
}

/** Get the Refresh Token — checks localStorage (remember_me=true) then sessionStorage */
export function getRefreshToken(): string | null {
  try {
    const local = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (local) return local;
    const session = sessionStorage.getItem(REFRESH_TOKEN_KEY);
    if (session) return session;
  } catch {
    // storage unavailable
  }
  return null;
}

/** Write the Refresh Token — stores in localStorage (remember_me=true) or sessionStorage (remember_me=false) */
export function setRefreshToken(token: string | null): void {
  const useLocalStorage = getRememberMe();
  try {
    if (token) {
      const storage = useLocalStorage ? localStorage : sessionStorage;
      const otherStorage = useLocalStorage ? sessionStorage : localStorage;
      storage.setItem(REFRESH_TOKEN_KEY, token);
      // Clear from the other storage to avoid stale tokens
      otherStorage.removeItem(REFRESH_TOKEN_KEY);
    } else {
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      sessionStorage.removeItem(REFRESH_TOKEN_KEY);
    }
  } catch {
    // storage unavailable
  }
}

/**
 * Set the "remember me" flag
 */
export function setRememberMe(value: boolean): void {
  try {
    localStorage.setItem(REMEMBER_ME_KEY, value ? '1' : '0');
  } catch {
    // localStorage unavailable
  }
}

/**
 * Get the "remember me" flag
 */
export function getRememberMe(): boolean {
  try {
    return localStorage.getItem(REMEMBER_ME_KEY) === '1';
  } catch {
    return false;
  }
}

/**
 * Get the "remember me" default — first-time users (no stored flag) default
 * to checked so the "30 天内免登录" promise actually takes effect without
 * the user having to discover the checkbox.
 */
export function getRememberMeDefault(): boolean {
  try {
    const stored = localStorage.getItem(REMEMBER_ME_KEY);
    return stored === null ? true : stored === '1';
  } catch {
    return true;
  }
}

const SAVED_USERNAME_KEY = 'gaf_saved_username';

/**
 * Save username (used when "remember me" login is enabled)
 */
export function setSavedUsername(username: string): void {
  try {
    localStorage.setItem(SAVED_USERNAME_KEY, username);
  } catch {
    // localStorage unavailable
  }
}

/**
 * Get the saved username
 */
export function getSavedUsername(): string | null {
  try {
    return localStorage.getItem(SAVED_USERNAME_KEY);
  } catch {
    return null;
  }
}

/** Clear all tokens and remember-me flag (clears all storage locations) */
export function clearTokens(): void {
  inMemoryAccessToken = null;
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REMEMBER_ME_KEY);
  localStorage.removeItem(SAVED_USERNAME_KEY);
  // Don't clear saved accounts — they persist across sessions for account switching
}

/**
 * Save account credentials for multi-account switching.
 * Updates existing entry if username already exists.
 * @param username - Account username
 * @param refreshToken - Refresh token for this account
 */
export function saveAccount(username: string, refreshToken: string): void {
  try {
    const accounts = getSavedAccounts();
    const existingIdx = accounts.findIndex((a) => a.username === username);
    const account: SavedAccount = {
      username,
      refreshToken,
      savedAt: new Date().toISOString(),
    };
    if (existingIdx >= 0) {
      accounts[existingIdx] = account;
    } else {
      accounts.push(account);
    }
    localStorage.setItem(SAVED_ACCOUNTS_KEY, JSON.stringify(accounts));
  } catch {
    // localStorage unavailable
  }
}

/**
 * Get all saved accounts from localStorage.
 * @returns Array of saved accounts (empty array if none or error)
 */
export function getSavedAccounts(): SavedAccount[] {
  try {
    const raw = localStorage.getItem(SAVED_ACCOUNTS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as SavedAccount[];
  } catch {
    return [];
  }
}

/**
 * Remove a saved account by username.
 * @param username - Account username to remove
 */
export function removeAccount(username: string): void {
  try {
    const accounts = getSavedAccounts();
    const filtered = accounts.filter((a) => a.username !== username);
    localStorage.setItem(SAVED_ACCOUNTS_KEY, JSON.stringify(filtered));
  } catch {
    // localStorage unavailable
  }
}

/** Parse JWT payload (signature not verified) */
export function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1];
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

/** Check if the Access Token is about to expire (default threshold 60 seconds) */
export function isTokenExpiringSoon(token: string | null, thresholdSeconds = 60): boolean {
  if (!token) return true;
  const payload = parseJwtPayload(token);
  if (!payload || !payload.exp) return true;
  const expMs = (payload.exp as number) * 1000;
  return Date.now() > expMs - thresholdSeconds * 1000;
}

/**
 * P1-4: Cross-tab synchronization via 'storage' event.
 * When another tab updates/clears the refresh token in localStorage, sync this tab.
 * - If token cleared (logout in another tab): clear local access token, trigger re-render.
 * - If token updated (refresh in another tab): no action needed — our access token stays valid until expiry.
 *
 * Call initCrossTabSync() once at app startup (main.tsx).
 */
let crossTabSyncInitialized = false;

export function initCrossTabSync(): void {
  if (crossTabSyncInitialized || typeof window === 'undefined') return;
  crossTabSyncInitialized = true;

  window.addEventListener('storage', (e: StorageEvent) => {
    if (e.key !== REFRESH_TOKEN_KEY || e.storageArea !== localStorage) return;

    if (e.newValue === null) {
      // Another tab logged out — clear this tab's tokens too
      inMemoryAccessToken = null;
      try {
        sessionStorage.removeItem(ACCESS_TOKEN_KEY);
      } catch {
        // sessionStorage unavailable
      }
      // Dispatch a custom event so React components can react (e.g. redirect to /login)
      window.dispatchEvent(new CustomEvent('gaf:auth-logout'));
    }
    // If e.newValue is a new token, another tab refreshed. Our access token is still
    // valid until it expires, so no immediate action needed. When it expires, our
    // refresh will use the new token from localStorage.
  });
}
