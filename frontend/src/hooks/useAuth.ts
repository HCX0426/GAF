/**
 * useAuth Hook
 *
 * wraps auth related operation status and method, provides concise API for component use.
 * includes:isRefreshing status,refreshToken method,logout method.
 */
import { useCallback, useEffect } from 'react';
import { useAuthStore } from '@/stores/useAuthStore';
import type { User } from '@/types/models';

/** useAuth return value API */
interface UseAuthReturn {
  /** current user */
  user: User | null;
  /** is no already auth */
  isAuthenticated: boolean;
  /** is no need to change password */
  mustChangePassword: boolean;
  /** is no currently load ( login process ) */
  loading: boolean;
  /** is no currently refresh Token */
  isRefreshing: boolean;
  /** user login */
  login: (username: string, password: string, rememberMe?: boolean) => Promise<void>;
  /** user logout ( clear has Token) */
  logout: () => Promise<void>;
  /** manually refresh Token */
  refreshToken: () => Promise<void>;
}

/**
 * auth Hook
 * component mount when auto call initAuth in progress silent recovery.
 */
export function useAuth(): UseAuthReturn {
  const {
    user,
    isAuthenticated,
    mustChangePassword,
    loading,
    isRefreshing,
    login,
    logout: storeLogout,
    refreshToken: storeRefreshToken,
    initAuth,
  } = useAuthStore();

  /** component mount when auto attempt silent recovery */
  useEffect(() => {
    initAuth();
  }, [initAuth]);

  /** logout, clear has Token and status */
  const logout = useCallback(async () => {
    await storeLogout();
  }, [storeLogout]);

  /** manually refresh Token */
  const refreshToken = useCallback(async () => {
    await storeRefreshToken();
  }, [storeRefreshToken]);

  return {
    user,
    isAuthenticated,
    mustChangePassword,
    loading,
    isRefreshing,
    login,
    logout,
    refreshToken,
  };
}

export default useAuth;
