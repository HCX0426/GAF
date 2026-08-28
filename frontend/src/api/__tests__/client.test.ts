/**
 * API Client unit tests.
 *
 * C21 fix: previous version imported a non-existent `createApiClient` named
 * export, expected `/api/v1` baseURL, and read `localStorage.getItem('token')`
 * — none of which matched the actual `client.ts` implementation.
 *
 * This rewrite tests the real default export `client` and mocks
 * `@/utils/tokenStore` so we can drive the request interceptor without
 * touching localStorage or in-memory token state.
 *
 * C1 (spec 2026-07-30): added trace_id interceptor tests — verifies
 * X-Trace-Id header is added from sessionStorage and response header is
 * persisted back to sessionStorage.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock tokenStore before importing the client so the interceptor uses our stubs.
vi.mock('@/utils/tokenStore', () => ({
  getAccessToken: vi.fn(() => null),
  setAccessToken: vi.fn(),
  getRefreshToken: vi.fn(() => null),
  setRefreshToken: vi.fn(),
  clearTokens: vi.fn(),
  isTokenExpiringSoon: vi.fn(() => false),
}));

import client from '@/api/client';
import { getAccessToken } from '@/utils/tokenStore';
import { setLastTraceId, getLastTraceId } from '@/utils/traceId';
import { API_PREFIX, API_TIMEOUT } from '@/config/app';
import type { InternalAxiosRequestConfig, AxiosResponse } from 'axios';

describe('API Client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: no access token in memory.
    (getAccessToken as ReturnType<typeof vi.fn>).mockReturnValue(null);
    // C1: clear sessionStorage trace_id between tests
    sessionStorage.clear();
  });

  it('exports a configured axios instance with v2 baseURL', () => {
    expect(client).toBeDefined();
    expect(client.defaults.baseURL).toBe(API_PREFIX);
    expect(client.defaults.timeout).toBe(API_TIMEOUT);
    expect(client.defaults.headers['Content-Type']).toBe('application/json');
  });

  it('request interceptor adds Authorization header when access token exists', async () => {
    (getAccessToken as ReturnType<typeof vi.fn>).mockReturnValue('test-jwt-token');

    const config = await client.interceptors.request.handlers![0].fulfilled({
      headers: {},
      url: '/accounts/auth/login/',
      method: 'post',
    } as InternalAxiosRequestConfig);

    expect(config.headers.Authorization).toBe('Bearer test-jwt-token');
    expect(getAccessToken).toHaveBeenCalled();
  });

  it('request interceptor does not add Authorization header when no token', async () => {
    const config = await client.interceptors.request.handlers![0].fulfilled({
      headers: {},
      url: '/accounts/auth/login/',
      method: 'post',
    } as InternalAxiosRequestConfig);

    expect(config.headers.Authorization).toBeUndefined();
  });

  // ---- C1 (spec 2026-07-30): trace_id interceptor tests ----

  it('C1: trace_id request interceptor adds X-Trace-Id header when sessionStorage has trace_id', async () => {
    setLastTraceId('550e8400-e29b-41d4-a716-446655440000');
    // trace_id interceptor is the second request interceptor (handlers[1])
    const traceInterceptor = client.interceptors.request.handlers![1];
    const config = await traceInterceptor.fulfilled({
      headers: {},
      url: '/tasks/1/execute/',
      method: 'post',
    } as InternalAxiosRequestConfig);

    expect(config.headers['X-Trace-Id']).toBe('550e8400-e29b-41d4-a716-446655440000');
  });

  it('C1: trace_id request interceptor does not add X-Trace-Id when sessionStorage empty', async () => {
    // No setLastTraceId call — sessionStorage empty
    const traceInterceptor = client.interceptors.request.handlers![1];
    const config = await traceInterceptor.fulfilled({
      headers: {},
      url: '/tasks/1/execute/',
      method: 'post',
    } as InternalAxiosRequestConfig);

    expect(config.headers['X-Trace-Id']).toBeUndefined();
  });

  it('C1: trace_id request interceptor does not overwrite existing X-Trace-Id header', async () => {
    setLastTraceId('session-trace-id');
    const traceInterceptor = client.interceptors.request.handlers![1];
    const config = await traceInterceptor.fulfilled({
      headers: { 'X-Trace-Id': 'preset-trace-id' },
      url: '/tasks/1/execute/',
      method: 'post',
    } as unknown as InternalAxiosRequestConfig);

    // Preset header should not be overwritten
    expect(config.headers['X-Trace-Id']).toBe('preset-trace-id');
  });

  it('C1: response interceptor reads X-Trace-Id header and updates sessionStorage', async () => {
    const responseInterceptor = client.interceptors.response.handlers![0];
    const response = {
      data: { id: 1, status: 'pending' },
      status: 200,
      statusText: 'OK',
      headers: { 'x-trace-id': 'backend-generated-trace-id' },
      config: { headers: {} } as InternalAxiosRequestConfig,
    } as AxiosResponse;

    await responseInterceptor.fulfilled(response);
    expect(getLastTraceId()).toBe('backend-generated-trace-id');
  });

  it('C1: response interceptor does not update sessionStorage when no X-Trace-Id header', async () => {
    setLastTraceId('existing-trace-id');
    const responseInterceptor = client.interceptors.response.handlers![0];
    const response = {
      data: { id: 1, status: 'pending' },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: { headers: {} } as InternalAxiosRequestConfig,
    } as unknown as AxiosResponse;

    await responseInterceptor.fulfilled(response);
    // Existing trace_id preserved (not cleared)
    expect(getLastTraceId()).toBe('existing-trace-id');
  });

  it('C1: response error interceptor reads X-Trace-Id from error response', async () => {
    const responseInterceptor = client.interceptors.response.handlers![0];
    const error = {
      name: 'AxiosError',
      message: 'Request failed with status 500',
      config: { _skipAuthRefresh: true } as InternalAxiosRequestConfig,
      response: {
        data: { detail: 'Server error' },
        status: 500,
        statusText: 'Internal Server Error',
        headers: { 'x-trace-id': 'error-trace-id' },
        config: {} as InternalAxiosRequestConfig,
      },
      isAxiosError: true,
    };

    // Error handler should reject (no 401 retry), but still read trace_id
    await expect(responseInterceptor.rejected!(error)).rejects.toBeDefined();
    expect(getLastTraceId()).toBe('error-trace-id');
  });
});
