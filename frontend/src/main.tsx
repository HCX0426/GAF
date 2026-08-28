/**
 * app render entry
 * init auth state and mount React app
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import { useAuthStore } from './stores/useAuthStore';
import { initCrossTabSync } from './utils/tokenStore';
import { installGlobalErrorHandlers } from './utils/reportFrontendError';
import App from './App';
import './App.css';
import './styles/acrylic.css';
import './styles/components.css';

// Set default dayjs locale globally (zh-cn) so that all dayjs() calls use it
dayjs.locale('zh-cn');

/**
 * TD-335 P0 #4: react-query QueryClient.
 * Stale time 30s matches the previous manual refetch cadence on most pages;
 * refetchOnWindowFocus off because device/task lists are polling-driven via
 * WebSocket subscriptions, not user-focus driven.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

/** P1-4: initialize cross-tab auth sync (storage event listener) */
initCrossTabSync();

/**
 * P0-10 (AI 可调试性, 2026-07-27): install window.onerror + unhandledrejection
 * listeners BEFORE React mounts. Catches render-external errors (e.g. async
 * callback throws, third-party script errors) and reports them to backend
 * via /api/v2/logs/frontend-errors/, so AI debugging can correlate frontend
 * crashes with backend/agent errors. ErrorBoundary handles React render
 * errors (installed in App.tsx); this catches everything else.
 */
installGlobalErrorHandlers();

/** init auth state (restored from localStorage/sessionStorage) */
useAuthStore.getState().initAuth();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
