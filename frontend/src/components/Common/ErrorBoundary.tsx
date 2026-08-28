/**
 * React Error Boundary component
 * catches child component render errors, shows friendly error page with retry button
 * supports custom fallback UI
 */
import { Component, type ReactNode, type ErrorInfo } from 'react';
import { Result, Button } from 'antd';
import { reportFrontendError } from '@/utils/reportFrontendError';

/** ErrorBoundary component props */
interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

/** ErrorBoundary component state */
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/** global error boundary component, catches child component render exceptions and shows friendly prompt */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  /** catches child component render errors and updates state */
  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  /** log error info to console and report to backend for AI debugging */
  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[ErrorBoundary] 捕获到渲染错误:', error, errorInfo);
    // P0-10 (AI 可调试性, 2026-07-27): 上报 React 渲染错误到后端,
    // 让 AI 调试时能区分 "前端渲染崩溃" vs "后端 500" vs "agent 执行失败"。
    // componentStack 是 React 特有的调用栈, 放在 extra 里供 AI 反推现场。
    void reportFrontendError({
      message: error.message || 'React render error',
      stack: error.stack,
      error_type: error.name,
      trigger: 'error_boundary',
      extra: { component_stack: errorInfo.componentStack },
    });
    this.props.onError?.(error, errorInfo);
  }

  /** retry button handler: reset error state */
  handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <Result
          status="error"
          title="页面渲染出错"
          subTitle={this.state.error?.message || '发生了未知错误，请尝试刷新页面'}
          extra={[
            <Button key="retry" type="primary" onClick={this.handleRetry}>
              重试
            </Button>,
            <Button key="refresh" onClick={() => window.location.reload()}>
              刷新页面
            </Button>,
          ]}
        />
      );
    }

    return this.props.children;
  }
}
