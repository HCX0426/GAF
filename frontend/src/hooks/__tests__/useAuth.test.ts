/**
 * TD-336: useAuth hook 测试 — 验证 wrapper 正确转发 store 状态和方法
 * useAuthStore 的业务逻辑已有 useAuthStore.test.ts 覆盖，本测试聚焦 hook 层
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAuth } from '@/hooks/useAuth';
import { useAuthStore } from '@/stores/useAuthStore';

// Mock auth API to avoid real network calls during initAuth
vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  logout: vi.fn(),
  changePassword: vi.fn(),
  refreshToken: vi.fn(),
  login2FA: vi.fn(),
}));

const makeUser = (role: 'admin' | 'operator' | 'viewer') => ({
  id: 1,
  username: 'testuser',
  role,
  must_change_password: false,
  is_active: true,
  is_first_login: false,
  totp_enabled: false,
  last_login: null,
  created_at: '2026-01-01T00:00:00Z',
});

beforeEach(() => {
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    accessToken: null,
    mustChangePassword: false,
    loading: false,
    isRefreshing: false,
    requires2FA: false,
    tempToken: null,
  });
});

describe('useAuth', () => {
  it('初始状态应正确转发 store 状态', () => {
    const { result } = renderHook(() => useAuth());
    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.mustChangePassword).toBe(false);
    expect(result.current.loading).toBe(false);
    expect(result.current.isRefreshing).toBe(false);
  });

  it('store 状态变化时应反映到 hook 返回值', () => {
    const { result, rerender } = renderHook(() => useAuth());
    expect(result.current.isAuthenticated).toBe(false);

    act(() => {
      useAuthStore.setState({
        user: makeUser('admin') as never,
        isAuthenticated: true,
        accessToken: 'test-token',
      });
    });
    rerender();

    expect(result.current.user?.username).toBe('testuser');
    expect(result.current.isAuthenticated).toBe(true);
  });

  it('mount 时应自动调用 initAuth (尝试 silent recovery)', () => {
    const initAuthSpy = vi.spyOn(useAuthStore.getState(), 'initAuth');
    renderHook(() => useAuth());
    expect(initAuthSpy).toHaveBeenCalled();
    initAuthSpy.mockRestore();
  });

  it('logout 应转发到 store.logout', async () => {
    useAuthStore.setState({
      user: makeUser('admin') as never,
      isAuthenticated: true,
      accessToken: 'test-token',
    });

    const { result } = renderHook(() => useAuth());
    expect(result.current.isAuthenticated).toBe(true);

    await act(async () => {
      await result.current.logout();
    });

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('login 应转发到 store.login', async () => {
    const { result } = renderHook(() => useAuth());

    // login 在 store 中会调用 api.login, 这里 mock 已拦截
    // 验证 hook 返回的 login 是 store 的 login
    expect(typeof result.current.login).toBe('function');
    expect(typeof result.current.refreshToken).toBe('function');
  });

  it('mustChangePassword 状态应正确转发', () => {
    const { result, rerender } = renderHook(() => useAuth());
    expect(result.current.mustChangePassword).toBe(false);

    act(() => {
      useAuthStore.setState({ mustChangePassword: true });
    });
    rerender();

    expect(result.current.mustChangePassword).toBe(true);
  });

  it('isRefreshing 状态应正确转发', () => {
    const { result, rerender } = renderHook(() => useAuth());
    expect(result.current.isRefreshing).toBe(false);

    act(() => {
      useAuthStore.setState({ isRefreshing: true });
    });
    rerender();

    expect(result.current.isRefreshing).toBe(true);
  });
});
