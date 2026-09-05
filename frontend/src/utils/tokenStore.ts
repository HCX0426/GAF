/**
 * Token & Multi-Account Storage Utilities
 *
 * Access Token in memory + sessionStorage backup (survives page refresh, cleared on tab close).
 * Refresh Token in sessionStorage ONLY (S6: never persisted to localStorage —
 *   survives page refresh but dies with the browser session, closing the
 *   30-day XSS-theft window that localStorage posed). "remember_me" now only
 *   controls username prefill + the checkbox default.
 * Multi-account credentials stored in sessionStorage (S6: same rationale —
 *   switching survives page refresh, not browser restarts).
 *
 * P1-5/P1-6: access token persisted to sessionStorage to reduce refresh calls on page reload.
 * P1-4: cross-tab sync via 'storage' event listener (legacy localStorage entries only).
 * S6 (2026-09-05): refresh token + saved accounts migrated off localStorage,
 *   with one-time cleanup of legacy entries in initCrossTabSync().
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

/** Get the Refresh Token — sessionStorage only (S6). Opportunistically drops legacy localStorage entries. */
export function getRefreshToken(): string | null {
  try {
    const session = sessionStorage.getItem(REFRESH_TOKEN_KEY);
    // S6 one-time migration: purge any pre-fix localStorage copy so an old
    // 30-day token can't linger on disk-backed storage.
    if (localStorage.getItem(REFRESH_TOKEN_KEY) !== null) {
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    }
    if (session) return session;
  } catch {
    // storage unavailable
  }
  return null;
}

/**
 * Write the Refresh Token — sessionStorage only (S6).
 * "remember_me" no longer changes the storage location; it only controls
 * username prefill / the checkbox default (see getRememberMeDefault).
 */
export function setRefreshToken(token: string | null): void {
  try {
    if (token) {
      sessionStorage.setItem(REFRESH_TOKEN_KEY, token);
    } else {
      sessionStorage.removeItem(REFRESH_TOKEN_KEY);
    }
    // Defensive: never leave a copy in localStorage (S6).
    localStorage.removeItem(REFRESH_TOKEN_KEY);
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
 * S6: stored in sessionStorage (not localStorage) — account switching survives
 * page refresh, not browser restarts.
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
    sessionStorage.setItem(SAVED_ACCOUNTS_KEY, JSON.stringify(accounts));
    // S6 one-time migration: purge the legacy localStorage copy.
    localStorage.removeItem(SAVED_ACCOUNTS_KEY);
  } catch {
    // sessionStorage unavailable
  }
}

/**
 * Get all saved accounts from sessionStorage.
 * @returns Array of saved accounts (empty array if none or error)
 */
export function getSavedAccounts(): SavedAccount[] {
  try {
    const raw = sessionStorage.getItem(SAVED_ACCOUNTS_KEY);
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
    sessionStorage.setItem(SAVED_ACCOUNTS_KEY, JSON.stringify(filtered));
  } catch {
    // sessionStorage unavailable
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
 * S6 (2026-09-05): the refresh token now lives in sessionStorage only, and
 * sessionStorage does not fire cross-tab 'storage' events — so logout in one
 * tab no longer propagates to other tabs. The listener below is kept solely
 * to react to legacy pre-S6 localStorage writes; initCrossTabSync() also
 * performs a one-time purge of legacy localStorage token/account entries.
 *
 * Call initCrossTabSync() once at app startup (main.tsx).
 */
let crossTabSyncInitialized = false;

export function initCrossTabSync(): void {
  if (crossTabSyncInitialized || typeof window === 'undefined') return;
  crossTabSyncInitialized = true;

  // S6 one-time migration: drop pre-fix localStorage copies of the refresh
  // token and saved accounts (even before any getRefreshToken() call).
  try {
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(SAVED_ACCOUNTS_KEY);
  } catch {
    // localStorage unavailable
  }

  window.addEventListener('storage', (e: StorageEvent) => {
    if (e.key !== REFRESH_TOKEN_KEY || e.storageArea !== localStorage) return;

    if (e.newValue === null) {
      // Another tab logged out (legacy pre-S6 flow) — clear this tab too
      inMemoryAccessToken = null;
      try {
        sessionStorage.removeItem(ACCESS_TOKEN_KEY);
        sessionStorage.removeItem(REFRESH_TOKEN_KEY);
      } catch {
        // sessionStorage unavailable
      }
      // Dispatch a custom event so React components can react (e.g. redirect to /login)
      window.dispatchEvent(new CustomEvent('gaf:auth-logout'));
    }
    // If e.newValue is a new token (legacy flow), no action needed — our
    // access token stays valid until expiry.
  });
}
