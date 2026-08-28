/**
 * Axios HTTP client instance
 *
 * Features:
 * - Request interceptor: auto-reads Access Token from memory and attaches to request headers
 * - Response interceptor: handles 401, attempts auto-refresh using Refresh Token
 * - Concurrency control: when multiple requests trigger refresh simultaneously, only one refresh request fires
 * - On refresh failure, auto-clears tokens and redirects to login page
 */
import axios, { type InternalAxiosRequestConfig, type AxiosResponse, type AxiosError } from 'axios';
import {
  getAccessToken,
  setAccessToken,
  getRefreshToken,
  setRefreshToken,
  clearTokens,
  isTokenExpiringSoon,
} from '@/utils/tokenStore';
import { getLastTraceId, setLastTraceId } from '@/utils/traceId';

import { API_PREFIX, API_TIMEOUT, TOKEN_REFRESH_THRESHOLD_SECONDS } from '@/config/app';

/**
 * F004 fix: extension to AxiosRequestConfig allowing specific requests to opt
 * out of the auth interceptors. Used by auth.ts:refreshToken() so it can call
 * client.post() (per audit F004) without triggering the request interceptor's
 * proactive-refresh logic or the response interceptor's 401-retry logic (both
 * of which would call performTokenRefresh() and create an infinite loop).
 */
declare module 'axios' {
  interface InternalAxiosRequestConfig {
    _skipAuthRefresh?: boolean;
    // L4: _retry flag set by 401 response interceptor to prevent
    // infinite retry loop on the same request.
    _retry?: boolean;
  }
  interface AxiosRequestConfig {
    _skipAuthRefresh?: boolean;
    _retry?: boolean;
  }
}

/** Simple error message extraction for interceptor logging */
function extractErrorDetail(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === 'string') return err;
  if (err && typeof err === 'object' && 'message' in err) return String((err as { message: unknown }).message);
  return 'Unknown error';
}

const client = axios.create({
  baseURL: API_PREFIX,
  timeout: API_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
  },
});

/** Refresh status: whether a refresh is currently in progress */
let isRefreshing = false;

/** Refresh wait queue: stores requests suspended due to concurrent refresh */
let refreshQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

/**
 * Process the refresh wait queue
 * @param error - On refresh failure, pass the error object
 * @param token - On refresh success, pass the new Access Token
 */
function processRefreshQueue(error: unknown | null, token: string | null = null): void {
  refreshQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token!);
    }
  });
  refreshQueue = [];
}

/**
 * Perform token refresh — exported so auth.ts can reuse the same mutex.
 * Uses a separate axios instance to avoid triggering interceptor loops.
 *
 * P0-1: Module-level refresh promise ensures only one refresh request is
 * in flight at any time across all callers (interceptors + initAuth + manual).
 */
let refreshPromise: Promise<string> | null = null;

export async function performTokenRefresh(): Promise<string> {
  // If a refresh is already in flight, wait for it (mutex)
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = doPerformTokenRefresh();
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

async function doPerformTokenRefresh(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }

  const response = await axios.post(
    `${API_PREFIX}/accounts/auth/refresh/`,
    { refresh: refreshToken },
    { headers: { 'Content-Type': 'application/json' } },
  );

  const newAccessToken: string = response.data.access;
  const newRefreshToken: string | undefined = response.data.refresh;

  setAccessToken(newAccessToken);
  if (newRefreshToken) {
    setRefreshToken(newRefreshToken);
  }

  return newAccessToken;
}

/**
 * P0-2: Classify refresh error to decide whether to clear tokens + redirect.
 * - Network error (no response / timeout): tokens may still be valid, keep them.
 * - 401 (token invalid/blacklisted): tokens are dead, clear + redirect.
 * - 5xx (server error): temporary issue, keep tokens for retry.
 * - Non-axios error: unknown, keep tokens.
 */
function isAuthError(err: unknown): boolean {
  if (axios.isAxiosError(err)) {
    return err.response?.status === 401 || err.response?.status === 403;
  }
  return false;
}

function isNetworkError(err: unknown): boolean {
  if (axios.isAxiosError(err)) {
    return !err.response; // No response = network/timeout error
  }
  return false;
}

/** P0-2: Handle refresh failure with error classification */
function handleRefreshFailure(error: unknown, context: string): void {
  if (isAuthError(error)) {
    // Token invalid/expired/blacklisted — must logout
    console.warn(`[axios] ${context}: token invalid, redirecting to login`);
    clearTokens();
    processRefreshQueue(error, null);
    window.location.replace('/login');
  } else if (isNetworkError(error)) {
    // Network error — keep tokens, user can retry
    console.warn(`[axios] ${context}: network error, tokens retained`);
    processRefreshQueue(error, null);
  } else {
    // 5xx or unknown — keep tokens, log warning
    console.warn(`[axios] ${context}: server error, tokens retained:`, extractErrorDetail(error));
    processRefreshQueue(error, null);
  }
}

/** Request interceptor: auto-attaches JWT Token and proactively refreshes when about to expire */
client.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    // F004 fix: requests marked _skipAuthRefresh (e.g. the refresh endpoint
    // itself) bypass the proactive token-refresh logic to avoid recursion.
    if (config._skipAuthRefresh) {
      return config;
    }
    const token = getAccessToken();

    if (token) {
      if (isTokenExpiringSoon(token, TOKEN_REFRESH_THRESHOLD_SECONDS)) {
        if (!isRefreshing) {
          isRefreshing = true;
          try {
            const newToken = await performTokenRefresh();
            processRefreshQueue(null, newToken);
            config.headers.Authorization = `Bearer ${newToken}`;
            return config;
          } catch (error) {
            // P0-2: classify error — only clear+redirect on auth error (401)
            handleRefreshFailure(error, 'request interceptor proactive refresh');
            if (isAuthError(error)) {
              return new Promise(() => {});
            }
            return Promise.reject(new Error(`Token refresh failed: ${extractErrorDetail(error)}`));
          } finally {
            isRefreshing = false;
          }
        } else {
          try {
            const newToken = await new Promise<string>((resolve, reject) => {
              refreshQueue.push({ resolve, reject });
            });
            config.headers.Authorization = `Bearer ${newToken}`;
            return config;
          } catch (err) {
            return Promise.reject(new Error(`Token refresh failed: ${extractErrorDetail(err)}`));
          }
        }
      } else {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

/**
 * C1 (spec 2026-07-30): trace_id 请求拦截器 — 从 sessionStorage 读 last_trace_id
 * 加 X-Trace-Id header。独立于 auth 拦截器, trace_id 在 auth 失败时仍需传递
 * (后端需 trace_id 关联匿名请求的日志, 如前端错误上报)。
 */
client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const traceId = getLastTraceId();
  if (traceId && !config.headers['X-Trace-Id']) {
    config.headers['X-Trace-Id'] = traceId;
  }
  return config;
});

/** Response interceptor: handles 401 unauthorized */
client.interceptors.response.use(
  (response: AxiosResponse) => {
    // C1: 读后端 X-Trace-Id 响应头, 更新 sessionStorage (后端是 trace_id 的
    // source of truth: 若后端生成了不同的 trace_id, 以前端收到的为准)
    const responseTraceId = response.headers?.['x-trace-id'];
    if (responseTraceId && typeof responseTraceId === 'string') {
      setLastTraceId(responseTraceId);
    }
    // P0-2 fix (AI 可调试性, 2026-07-27): unwrap unified response envelope.
    // Backend UnifiedResponseMiddleware wraps all JSON responses as
    // { code, message, data }. Frontend expects raw payload in response.data,
    // so unwrap here: if response.data has the unified shape AND code !== 0,
    // reject as error (non-zero code = business error). If code === 0,
    // replace response.data with the inner data payload.
    // Backward compat: if response.data does NOT have the unified shape
    // (unified_response disabled or non-JSON), pass through unchanged.
    const payload = response.data;
    if (payload && typeof payload === 'object' && 'code' in payload && 'message' in payload && 'data' in payload) {
      const unified = payload as { code: number; message: string; data: unknown };
      if (unified.code !== 0) {
        // Business error — reject so error handlers catch it.
        // Preserve status code + unified code for diagnostics.
        const error: AxiosError & { businessCode?: number; businessMessage?: string } = {
          ...new Error(unified.message || 'Business error'),
          name: 'AxiosError',
          config: response.config,
          response: {
            ...response,
            data: unified.data,
          },
          isAxiosError: true,
          businessCode: unified.code,
          businessMessage: unified.message,
        } as AxiosError & { businessCode?: number; businessMessage?: string };
        return Promise.reject(error);
      }
      // Success — unwrap: replace response.data with inner payload.
      response.data = unified.data;
    }
    return response;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig;

    // C1: 错误响应也读 X-Trace-Id (后端 4xx/5xx 仍会返回 trace_id header,
    // 前端调试时需关联后端日志)
    const errorTraceId = error.response?.headers?.['x-trace-id'];
    if (errorTraceId && typeof errorTraceId === 'string') {
      setLastTraceId(errorTraceId);
    }

    // F004 fix: skip 401-retry logic for requests that opted out (e.g. the
    // refresh endpoint itself — its 401 means the refresh token is invalid,
    // not that we should try refreshing again).
    if (error.response?.status === 401 && !originalRequest._retry && !originalRequest._skipAuthRefresh) {
      const refreshToken = getRefreshToken();

      if (refreshToken) {
        if (!isRefreshing) {
          isRefreshing = true;
          originalRequest._retry = true;

          try {
            const newToken = await performTokenRefresh();
            processRefreshQueue(null, newToken);
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return client(originalRequest);
          } catch (refreshError) {
            // P0-2: classify error — only clear+redirect on auth error (401)
            handleRefreshFailure(refreshError, 'response interceptor 401 retry');
            if (isAuthError(refreshError)) {
              return new Promise(() => {});
            }
            return Promise.reject(refreshError);
          } finally {
            isRefreshing = false;
          }
        } else {
          return new Promise((resolve, reject) => {
            refreshQueue.push({
              resolve: (token: string) => {
                originalRequest.headers.Authorization = `Bearer ${token}`;
                resolve(client(originalRequest));
              },
              reject: (err: unknown) => {
                console.warn('[axios] Concurrent request rejected during token refresh:', extractErrorDetail(err));
                reject(err);
              },
            });
          });
        }
      }

      clearTokens();
      processRefreshQueue(new Error('Authentication failed'), null);
      // M16+M17: already using replace (consistent with useAuthStore.ts).
      window.location.replace('/login');
      // M18: never-resolving promise suppresses UI error flicker during redirect.
      return new Promise(() => {});
    }

    return Promise.reject(error);
  },
);

export default client;
