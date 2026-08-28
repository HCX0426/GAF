/**
 * auth status management Store
 *
 * management user info,Token(Access storage inside storage,Refresh storage localStorage),
 * login / logout / change password / refresh Token etc. operation.
 */
import { create } from 'zustand';
import axios from 'axios';
import {
  login as apiLogin,
  logout as apiLogout,
  changePassword as apiChangePassword,
  refreshToken as apiRefreshToken,
  login2FA as apiLogin2FA,
} from '@/api/auth';
import { fetchCurrentUser } from '@/api/misc';
import {
  setAccessToken,
  getRefreshToken,
  setRefreshToken,
  clearTokens,
  setRememberMe,
  setSavedUsername,
  saveAccount as saveAccountToStore,
  getSavedAccounts,
  removeAccount as removeAccountFromStore,
} from '@/utils/tokenStore';
import type { User } from '@/types/models';
import type { SavedAccount } from '@/utils/tokenStore';
import { getErrorMessage } from '@/utils/errorHandler';

/** P0-2: Classify errors — only auth errors (401/403) should clear tokens + redirect */
function isAuthError(err: unknown): boolean {
  if (axios.isAxiosError(err)) {
    return err.response?.status === 401 || err.response?.status === 403;
  }
  return false;
}

/** Auth Store state interface */
interface AuthState {
  /**
   * Current user info. Typed as `User & { is_first_login?: boolean }`
   * because the login endpoint (`CustomTokenObtainPairSerializer.validate`)
   * attaches `is_first_login` to the response `user` dict at runtime
   * (computed from `user.last_login is None`). `useAuthStore` stores the
   * login response `user` directly into this field, so consumers can
   * read `user?.is_first_login`. Not part of the `User` schema.
   */
  user: (User & { is_first_login?: boolean }) | null;
  /** Whether authenticated */
  isAuthenticated: boolean;
  /** In-memory access token (mirrors tokenStore for React reactivity) */
  accessToken: string | null;
  /** Whether first login requires password change */
  mustChangePassword: boolean;
  /** Login/refresh loading state */
  loading: boolean;
  /** Whether token refresh is in progress */
  isRefreshing: boolean;
  /** Whether 2FA verification is required */
  requires2FA: boolean;
  /** Temporary token for 2FA flow */
  tempToken: string | null;
  /** User login */
  login: (username: string, password: string, rememberMe?: boolean) => Promise<void>;
  /** User logout */
  logout: () => Promise<void>;
  /** Change password */
  changePassword: (oldPassword: string, newPassword: string) => Promise<void>;
  /** 2FA login step 2 */
  login2FA: (totpCode: string, rememberMe?: boolean) => Promise<void>;
  /** Initialize auth state (silent recovery on page load) */
  initAuth: () => Promise<void>;
  /** Manual token refresh */
  refreshToken: () => Promise<void>;
  /** Set user info */
  setUser: (user: User & { is_first_login?: boolean }) => void;
  /** Refresh current user info from backend */
  refreshUser: () => Promise<void>;
  /** Clear 2FA state */
  clear2FA: () => void;
  /** Switch to another saved account by username */
  switchAccount: (username: string) => Promise<void>;
  /** Get all saved accounts for display */
  getSavedAccountsList: () => SavedAccount[];
  /** Remove a saved account from storage */
  removeSavedAccount: (username: string) => void;
}

/** auth status management */
export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAuthenticated: false,
  accessToken: null,
  mustChangePassword: false,
  loading: false,
  isRefreshing: false,
  requires2FA: false,
  tempToken: null,

  /** User login, save tokens to memory/localStorage on success */
  login: async (username: string, password: string, rememberMe = false) => {
    set({ loading: true });
    try {
      const res = await apiLogin({ username, password, remember_me: rememberMe });
      setRememberMe(rememberMe);
      if (rememberMe) {
        setSavedUsername(username);
      }
      if (res.requires_2fa && res.temp_token) {
        set({
          requires2FA: true,
          tempToken: res.temp_token,
          loading: false,
        });
        return;
      }
      /** Auto-save account credentials on successful login */
      const rt = getRefreshToken();
      if (rt) {
        saveAccountToStore(username, rt);
      }
      if (res.access) {
        setAccessToken(res.access);
      }
      set({
        user: res.user,
        isAuthenticated: true,
        accessToken: res.access ?? null,
        mustChangePassword: res.must_change_password ?? false,
        loading: false,
      });
    } catch (error) {
      set({ loading: false });
      // Re-throw original error so callers can classify (network/auth/2FA) accurately
      throw error;
    }
  },

  /** user logout, clear inside storage Token and localStorage and reset status */
  logout: async () => {
    try {
      await apiLogout();
    } catch (err) {
      console.warn('[authStore] Logout API call failed:', getErrorMessage(err));
    } finally {
      // C2 fix: explicitly clear tokens even if logout API failed — prevents
      // session-fixation where stale tokens persist on network/401 errors.
      clearTokens();
      set({
        user: null,
        isAuthenticated: false,
        accessToken: null,
        mustChangePassword: false,
      });
    }
  },

  /** change password, success after clear mustChangePassword mark */
  changePassword: async (oldPassword: string, newPassword: string) => {
    await apiChangePassword({ old_password: oldPassword, new_password: newPassword });
    set({ mustChangePassword: false });
  },

  /** page load when silent recovery auth: use Refresh Token exchange for new Access Token */
  initAuth: async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      return;
    }

    set({ isRefreshing: true });
    try {
      const res = await apiRefreshToken();
      if (res.access) {
        setAccessToken(res.access);
      }
      // get user info
      try {
        const user = await fetchCurrentUser();
        set({
          user,
          isAuthenticated: true,
          accessToken: res.access ?? null,
          isRefreshing: false,
        });
      } catch (err) {
        console.warn('[authStore] initAuth: Failed to fetch user info:', getErrorMessage(err));
        set({ isAuthenticated: true, accessToken: res.access ?? null, isRefreshing: false });
      }
    } catch (err) {
      // P0-2: classify error — only clear tokens + redirect on auth error (401)
      // Network/server errors retain tokens so user can retry
      if (isAuthError(err)) {
        clearTokens();
        set({ isRefreshing: false, user: null, isAuthenticated: false, accessToken: null });
        if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
          window.location.replace('/login');
        }
      } else {
        // Network error / server error — keep tokens, user can retry
        console.warn('[authStore] initAuth: Network/server error, tokens retained:', getErrorMessage(err));
        set({ isRefreshing: false });
      }
    }
  },

  /** manually refresh Token */
  refreshToken: async () => {
    set({ isRefreshing: true });
    try {
      const res = await apiRefreshToken();
      setAccessToken(res.access);
      set({ accessToken: res.access, isRefreshing: false });
    } catch (err) {
      // P0-2: classify error — only clear on auth error
      if (isAuthError(err)) {
        clearTokens();
        set({
          user: null,
          isAuthenticated: false,
          accessToken: null,
          isRefreshing: false,
        });
        throw new Error(`Token 刷新失败: ${getErrorMessage(err)}`, { cause: err });
      } else {
        // Network/server error — keep tokens, don't logout
        set({ isRefreshing: false });
        throw new Error(`Token 刷新失败（网络/服务器错误，token 已保留）: ${getErrorMessage(err)}`, { cause: err });
      }
    }
  },

  /** settings user info ( used for change password after update local status ) */
  setUser: (user: User & { is_first_login?: boolean }) => {
    set({ user });
  },

  /** re- pull current user info */
  refreshUser: async () => {
    try {
      const user = await fetchCurrentUser();
      set({ user });
    } catch (err) {
      console.warn('[authStore] refreshUser failed:', getErrorMessage(err));
      throw err;
    }
  },

  /** 2FA login step 2 */
  login2FA: async (totpCode: string, rememberMe = false) => {
    const { tempToken } = get();
    if (!tempToken) {
      throw new Error('No temp token available');
    }
    set({ loading: true });
    try {
      const res = await apiLogin2FA({
        temp_token: tempToken,
        totp_code: totpCode,
        remember_me: rememberMe,
      });
      if (res.access) {
        setAccessToken(res.access);
      }
      // P2-8: save account credentials for multi-account switching (was missing in 2FA flow)
      setRememberMe(rememberMe);
      if (rememberMe && res.user?.username) {
        setSavedUsername(res.user.username);
        const rt = getRefreshToken();
        if (rt) {
          saveAccountToStore(res.user.username, rt);
        }
      }
      set({
        user: res.user,
        isAuthenticated: true,
        accessToken: res.access ?? null,
        mustChangePassword: res.must_change_password,
        requires2FA: false,
        tempToken: null,
        loading: false,
      });
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  /** Clear 2FA state */
  clear2FA: () => {
    set({ requires2FA: false, tempToken: null });
  },

  /**
   * Switch to a saved account by using its stored refresh token.
   * Clears current state, sets the target refresh token, then calls initAuth.
   * @param username - Target account username to switch to
   */
  switchAccount: async (username: string) => {
    const accounts = getSavedAccounts();
    const target = accounts.find((a) => a.username === username);
    if (!target) {
      throw new Error(`Account "${username}" not found in saved accounts`);
    }
    /** Clear current session first */
    set({
      user: null,
      isAuthenticated: false,
      accessToken: null,
      loading: true,
    });
    clearTokens();
    /** Set target refresh token and re-initialize */
    setRefreshToken(target.refreshToken);
    try {
      const res = await apiRefreshToken();
      if (res.access) {
        setAccessToken(res.access);
      }
      const user = await fetchCurrentUser();
      set({
        user,
        isAuthenticated: true,
        accessToken: res.access ?? null,
        loading: false,
      });
    } catch (err) {
      // P0-2: classify error — only clear tokens on auth error
      if (isAuthError(err)) {
        clearTokens();
        set({ accessToken: null, loading: false });
        throw new Error(`切换账户 "${username}" 失败：凭证可能已过期`, { cause: err });
      } else {
        // Network/server error — don't clear, user can retry
        set({ loading: false });
        throw new Error(`切换账户 "${username}" 失败（网络错误，请重试）`, { cause: err });
      }
    }
  },

  /**
   * Get all saved accounts for display in AccountSwitcher dropdown.
   * @returns Array of SavedAccount objects
   */
  getSavedAccountsList: (): SavedAccount[] => {
    return getSavedAccounts();
  },

  /**
   * Remove a saved account from localStorage storage.
   * @param username - Username of account to remove
   */
  removeSavedAccount: (username: string) => {
    removeAccountFromStore(username);
  },
}));
