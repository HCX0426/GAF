/**
 * login status route guard component
 * not logged in when redirect to login page, already login render child component
 * supports wait initial start transform auth complete ( used for remember-me feature silent recovery )
 */
import { type ReactNode, useEffect, useRef, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuthStore } from '@/stores/useAuthStore';

/** AuthGuard component props */
interface AuthGuardProps {
  children: ReactNode;
  fallbackPath?: string;
}

/** login status route guard */
export function AuthGuard({ children, fallbackPath = '/login' }: AuthGuardProps) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isRefreshing = useAuthStore((s) => s.isRefreshing);
  const [isInitialized, setIsInitialized] = useState(false);
  /** Track the polling timer so it can be cleaned up on unmount */
  const initTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** wait initial start transform auth complete */
  useEffect(() => {
    let cancelled = false;

    /** check is no currently refresh token(initAuth in progress in ) */
    const checkInit = () => {
      if (cancelled) return;

      const state = useAuthStore.getState();
      if (state.isRefreshing) {
        // currently refresh in,100ms after again check
        initTimerRef.current = setTimeout(checkInit, 100);
      } else {
        // refresh complete or no needs refresh
        setIsInitialized(true);
      }
    };

    checkInit();

    return () => {
      cancelled = true;
      if (initTimerRef.current) clearTimeout(initTimerRef.current);
    };
  }, []);

  /** show load status directly to initial start transform complete */
  if (!isInitialized || isRefreshing) {
    return (
      <div
        className="gaf-flex-center"
        style={{
          justifyContent: 'center',
          height: '100vh',
          width: '100vw',
        }}
      >
        <Spin size="large" description="正在验证身份..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to={fallbackPath} replace />;
  }

  return <>{children}</>;
}

export default AuthGuard;
