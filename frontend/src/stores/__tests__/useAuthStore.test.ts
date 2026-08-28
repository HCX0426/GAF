import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore } from '@/stores/useAuthStore';
import * as tokenStore from '@/utils/tokenStore';

// Mock the auth API layer so the store can be tested in isolation.
vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  logout: vi.fn(),
  changePassword: vi.fn(),
  refreshToken: vi.fn(),
  login2FA: vi.fn(),
}));

describe('authStore', () => {
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
    tokenStore.clearTokens();
    localStorage.clear();
  });

  it('initial state should be unauthenticated', () => {
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.mustChangePassword).toBe(false);
  });

  it('setUser should update user info', () => {
    const { setUser } = useAuthStore.getState();
    const user = {
      id: 1,
      username: 'testuser',
      role: 'viewer',
      must_change_password: false,
      is_active: true,
      is_first_login: false,
      totp_enabled: false,
      last_login: null,
      created_at: '2026-01-01T00:00:00Z',
    };
    setUser(user as import('@/types/models').User);

    const state = useAuthStore.getState();
    expect(state.user?.username).toBe('testuser');
  });

  it('logout should clear auth state', async () => {
    useAuthStore.setState({
      user: { id: 1, username: 'testuser' } as import('@/types/models').User,
      isAuthenticated: true,
      accessToken: 'test-access-token',
    });

    const { logout } = useAuthStore.getState();
    await logout();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
  });

  it('clear2FA should reset 2FA state', () => {
    useAuthStore.setState({ requires2FA: true, tempToken: 'temp' });

    const { clear2FA } = useAuthStore.getState();
    clear2FA();

    const state = useAuthStore.getState();
    expect(state.requires2FA).toBe(false);
    expect(state.tempToken).toBeNull();
  });
});
