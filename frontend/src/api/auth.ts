/**
 * auth related API
 * includes login (supports remember_me), refresh Token, logout, change password interfaces
 */
import client, { performTokenRefresh } from './client';
import type {
  LoginRequest,
  LoginResponse,
  RefreshTokenResponse,
  ChangePasswordRequest,
  TOTPSetupResponse,
  Login2FARequest,
  UserSession,
  InitStatus,
} from '@/types/models';
import { setAccessToken, setRefreshToken, getRefreshToken, clearTokens, setRememberMe } from '@/utils/tokenStore';
import { API_PREFIX } from '@/config/app';

/**
 * Fetch system init status.
 * Endpoint: GET /accounts/init/status/
 * Lives on the init domain but init.ts is read-only in this refactor scope,
 * so the helper is exposed here for the login flow.
 */
export async function getInitStatus(options?: { signal?: AbortSignal }): Promise<InitStatus> {
  const res = await client.get<InitStatus>('/accounts/init/status/', { signal: options?.signal });
  return res.data;
}

/** user login, supports remember_me parameter */
export async function login(data: LoginRequest): Promise<LoginResponse> {
  const payload: Record<string, unknown> = {
    username: data.username,
    password: data.password,
    remember_me: data.remember_me ?? false,
  };
  // _skipAuthRefresh: login endpoint returns 401 for wrong credentials — this
  // is a normal business flow, NOT a token-expiry event. Without this flag the
  // response interceptor (client.ts L231) treats 401 as "token expired", tries
  // refresh, then on failure calls window.location.replace('/login') and
  // returns a never-resolving promise — the page reloads, message.error() is
  // wiped, and the user sees no "wrong credentials" feedback (N160).
  const res = await client.post<LoginResponse>('/accounts/auth/login/', payload, {
    _skipAuthRefresh: true,
  });

  // P0-4: setRememberMe MUST be called BEFORE setRefreshToken — setRefreshToken
  // reads getRememberMe() to decide storage location (localStorage for 30-day
  // persistence vs sessionStorage for session-only). Wrong order causes refresh
  // token to land in sessionStorage even when remember_me=true, breaking the
  // "30-day remember me" feature (token lost on browser close).
  if (data.remember_me) {
    setRememberMe(true);
  }
  if (res.data.access) {
    setAccessToken(res.data.access);
  }
  if (res.data.refresh) {
    setRefreshToken(res.data.refresh);
  }

  return res.data;
}

/**
 * Refresh access token — P0-1 fix: reuses client.ts's performTokenRefresh()
 * to share the same module-level mutex (refreshPromise).
 *
 * Previously used client.post() with _skipAuthRefresh to bypass interceptors,
 * but this bypassed the isRefreshing mutex too, causing concurrent refresh
 * race conditions when initAuth + request interceptor fired simultaneously.
 *
 * Now delegates to performTokenRefresh() which:
 * 1. Uses a module-level refreshPromise (only one refresh in flight)
 * 2. Sets tokens via tokenStore (same as before)
 * 3. Returns the new access token string
 *
 * The returned RefreshTokenResponse shape is preserved for caller compatibility.
 */
export async function refreshToken(): Promise<RefreshTokenResponse> {
  const newAccessToken = await performTokenRefresh();
  // performTokenRefresh already set access + refresh tokens via tokenStore
  // Return response shape for callers that read res.access
  return { access: newAccessToken } as RefreshTokenResponse;
}

/** user logout ( add current Refresh Token to blacklist ) */
export async function logout(): Promise<void> {
  const currentRefreshToken = getRefreshToken();
  // C2 fix: clear tokens in finally so network/401 errors don't leave them in localStorage.
  try {
    if (currentRefreshToken) {
      await client.post('/accounts/auth/logout/', { refresh: currentRefreshToken });
    }
  } finally {
    clearTokens();
  }
}

/** change password */
export async function changePassword(data: ChangePasswordRequest): Promise<void> {
  await client.post('/accounts/auth/change-password/', data);
}

/** user register */
export async function register(data: {
  username: string;
  email?: string;
  password: string;
  confirm_password: string;
}): Promise<LoginResponse> {
  const res = await client.post<LoginResponse>('/accounts/auth/register/', data);
  if (res.data.access) {
    setAccessToken(res.data.access);
  }
  if (res.data.refresh) {
    setRefreshToken(res.data.refresh);
  }
  return res.data;
}

/** get OAuth login URL */
export function getOAuthUrl(provider: 'github' | 'google'): string {
  return `${API_PREFIX}/accounts/auth/oauth/${provider}/`;
}

/** 2FA setup - get secret and QR Code URI */
export async function setup2FA(): Promise<TOTPSetupResponse> {
  const res = await client.post<TOTPSetupResponse>('/accounts/auth/2fa/setup/');
  return res.data;
}

/** 2FA verify settings - verify TOTP code to complete setup */
export async function verify2FASetup(totpCode: string): Promise<void> {
  await client.post('/accounts/auth/2fa/verify-setup/', { totp_code: totpCode });
}

/** 2FA disable - requires password confirmation */
export async function disable2FA(password: string): Promise<void> {
  await client.post('/accounts/auth/2fa/disable/', { password });
}

/** login step 2 - 2FA verify */
export async function login2FA(data: Login2FARequest): Promise<LoginResponse> {
  // _skipAuthRefresh: same as login() — 2FA endpoint returns 401 for wrong
  // codes, which is a business flow, not token expiry (N160).
  const res = await client.post<LoginResponse>('/accounts/auth/login-2fa/', data, {
    _skipAuthRefresh: true,
  });

  // P0-4: setRememberMe before setRefreshToken (same fix as login() above)
  if (data.remember_me) {
    setRememberMe(true);
  }
  if (res.data.access) {
    setAccessToken(res.data.access);
  }
  if (res.data.refresh) {
    setRefreshToken(res.data.refresh);
  }

  return res.data;
}

/** request password reset ( send reset link to email ) */
export async function requestPasswordReset(email: string): Promise<{ detail: string; reset_token?: string }> {
  const res = await client.post('/accounts/auth/password-reset/', { email });
  return res.data;
}

/** confirm password reset ( use Token to set new password ) */
export async function confirmPasswordReset(data: {
  token: string;
  new_password: string;
  confirm_password: string;
}): Promise<{ detail: string }> {
  const res = await client.post('/accounts/auth/password-reset/confirm/', data);
  return res.data;
}

/** get current user has active session ( login device list ) */
export async function fetchSessions(): Promise<UserSession[]> {
  const res = await client.get<UserSession[]>('/accounts/auth/sessions/');
  return res.data;
}

/** kick offline specific session */
export async function kickSession(id: number): Promise<{ detail: string }> {
  const res = await client.delete<{ detail: string }>(`/accounts/auth/sessions/${id}/`);
  return res.data;
}

/** kick offline all other sessions except current */
export async function logoutAllOtherSessions(): Promise<{ detail: string }> {
  const res = await client.post<{ detail: string }>('/accounts/auth/sessions/logout-all-others/');
  return res.data;
}
