/**
 * Page-level ErrorBoundary for lazy-loaded routes.
 *
 * Wraps each lazy page inside <Lazy> (App.tsx). Distinct from the root
 * <ErrorBoundary> in two ways:
 * 1. Differentiates chunk-load failures (network / stale chunk hash) from
 *    page render errors, surfacing the right recovery affordance.
 * 2. "Retry" remounts children via a key bump — for chunk errors this
 *    re-triggers the dynamic import; for render errors this re-runs
 *    initial render. Either way the rest of the SPA stays alive because
 *    the failure never bubbles to the root boundary.
 *
 * Default fallback UI is provided; pass `fallback` to override for
 * non-page contexts. Recovery buttons are hidden when the host app
 * supplies its own fallback.
 */
import { Component, type ReactNode, type ErrorInfo } from 'react';
import { Result, Button, Space } from 'antd';
import { reportFrontendError } from '@/utils/reportFrontendError';

/** Error message patterns emitted by bundlers when a dynamic import fails.
 *  Covers Webpack ("Loading chunk N failed") and Vite/ESM native dynamic
 *  import failures. Order does not matter; first match wins. */
const CHUNK_LOAD_ERROR_PATTERNS: ReadonlyArray<RegExp> = [
  /Loading chunk \d+ failed/i,
  /Loading CSS chunk \d+ failed/i,
  /Failed to fetch dynamically imported module/i,
  /Importing a module script failed/i,
  /error loading dynamically imported module/i,
  /Unable to preload CSS for/i,
];

/** Returns true when the captured error looks like a bundler chunk-load
 *  failure rather than a render-time throw. */
function isChunkLoadError(error: Error | null): boolean {
  if (!error) return false;
  const message = error.message || '';
  return CHUNK_LOAD_ERROR_PATTERNS.some((pattern) => pattern.test(message));
}

export interface PageErrorBoundaryProps {
  children: ReactNode;
  /** Optional page label shown in the error title for easier debugging. */
  pageName?: string;
  /** Optional override for the entire fallback UI. When provided, the
   *  boundary still captures errors but renders this node verbatim. */
  fallback?: ReactNode;
  /** Optional error hook (e.g. for telemetry). Called on every catch. */
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface PageErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  /** Incremented on each retry; used as React key on the children wrapper
   *  so React discards the crashed subtree and remounts it. */
  retryKey: number;
}

export default class PageErrorBoundary extends Component<PageErrorBoundaryProps, PageErrorBoundaryState> {
  state: PageErrorBoundaryState = {
    hasError: false,
    error: null,
    retryKey: 0,
  };

  static getDerivedStateFromError(error: Error): Partial<PageErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[PageErrorBoundary] page-level error caught:', error, errorInfo);
    // C2 (spec 2026-07-30): 上报页面级渲染错误到后端, 让 AI 调试时能区分
    // "页面渲染崩溃" vs "根组件渲染崩溃" vs "后端 500" vs "agent 执行失败"。
    // componentStack 放在 extra 里供 AI 反推现场。
    void reportFrontendError({
      message: error.message || 'Page render error',
      stack: error.stack,
      error_type: error.name,
      trigger: 'error_boundary',
      extra: { component_stack: errorInfo.componentStack, boundary: 'page' },
    });
    this.props.onError?.(error, errorInfo);
  }

  /** Reset error state and bump retryKey so children remount — this
   *  re-triggers lazy import for chunk errors and re-runs render for
   *  render errors, without affecting sibling routes. */
  handleRetry = (): void => {
    this.setState((prev) => ({
      hasError: false,
      error: null,
      retryKey: prev.retryKey + 1,
    }));
  };

  /** Navigate to /dashboard via full location assign. SPA navigate is
   *  avoided because the React Router context may be inconsistent after
   *  a render crash; a hard route change guarantees clean state. */
  handleGoHome = (): void => {
    this.setState({ hasError: false, error: null });
    window.location.assign('/dashboard');
  };

  render(): ReactNode {
    const { hasError, error, retryKey } = this.state;
    const { children, pageName, fallback } = this.props;

    if (!hasError) {
      // key bump forces React to discard the crashed subtree and remount
      // children on retry — this is what actually re-runs the lazy import.
      return <div key={retryKey}>{children}</div>;
    }

    if (fallback) {
      return fallback;
    }

    const chunkLoadError = isChunkLoadError(error);
    const title = pageName
      ? `${pageName} · ${chunkLoadError ? '页面资源加载失败' : '页面渲染出错'}`
      : chunkLoadError
        ? '页面资源加载失败'
        : '页面渲染出错';

    if (chunkLoadError) {
      return (
        <Result
          status="warning"
          title={title}
          subTitle="可能是网络异常或页面资源已更新。点击「重试」重新加载该页；若仍失败，请返回首页后重试。"
          extra={
            <Space>
              <Button type="primary" onClick={this.handleRetry}>
                重试
              </Button>
              <Button onClick={this.handleGoHome}>返回首页</Button>
            </Space>
          }
        />
      );
    }

    return (
      <Result
        status="error"
        title={title}
        subTitle={error?.message || '发生了未知错误，请重试或返回首页。'}
        extra={
          <Space>
            <Button type="primary" onClick={this.handleRetry}>
              重试
            </Button>
            <Button onClick={this.handleGoHome}>返回首页</Button>
          </Space>
        }
      />
    );
  }
}
