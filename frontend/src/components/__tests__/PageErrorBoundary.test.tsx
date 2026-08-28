import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock, MockInstance } from 'vitest';
import type { ReactNode } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import PageErrorBoundary from '@/components/Common/PageErrorBoundary';

// C2: mock reportFrontendError 避免测试发真实网络请求
vi.mock('@/utils/reportFrontendError', () => ({
  reportFrontendError: vi.fn().mockResolvedValue(undefined),
}));

import { reportFrontendError } from '@/utils/reportFrontendError';

function ChunkLoadThrower(): ReactNode {
  throw new Error('Loading chunk 42 failed.');
}

function RenderErrorThrower(): ReactNode {
  throw new Error('render boom: undefined is not a function');
}

/** jsdom's window.location is an accessor with non-configurable members,
 *  so neither vi.spyOn(window.location, 'assign') nor Object.defineProperty
 *  on assign works ("Cannot redefine property"). Instead we replace the
 *  whole location getter on window with a shallow clone carrying a mock
 *  assign — clean restore in afterEach keeps the suite leak-free. */
function mockLocationAssign(): Mock {
  const fn = vi.fn();
  const original = window.location;
  const stub = { ...original, assign: fn };
  vi.spyOn(window, 'location', 'get').mockReturnValue(stub);
  return fn;
}

describe('PageErrorBoundary', () => {
  let consoleSpy: MockInstance;
  let locationSpy: MockInstance;

  beforeEach(() => {
    consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    locationSpy = mockLocationAssign();
    vi.clearAllMocks();
  });

  afterEach(() => {
    consoleSpy.mockRestore();
    locationSpy.mockRestore();
  });

  it('renders children when no error is thrown', () => {
    render(
      <PageErrorBoundary>
        <div>healthy page</div>
      </PageErrorBoundary>,
    );
    expect(screen.getByText('healthy page')).toBeInTheDocument();
  });

  it('shows chunk-load UI with retry + go-home buttons when a chunk load error is caught', () => {
    render(
      <PageErrorBoundary>
        <ChunkLoadThrower />
      </PageErrorBoundary>,
    );
    expect(screen.getByText('页面资源加载失败')).toBeInTheDocument();
    // antd v6 inserts a space between CJK chars in 2-char button labels
    // ("重试" renders as "重 试"); regex tolerates that spacing.
    expect(screen.getByRole('button', { name: /重\s?试/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '返回首页' })).toBeInTheDocument();
  });

  it('shows render-error UI with the error message when a render throw is caught', () => {
    render(
      <PageErrorBoundary>
        <RenderErrorThrower />
      </PageErrorBoundary>,
    );
    expect(screen.getByText('页面渲染出错')).toBeInTheDocument();
    expect(screen.getByText(/render boom/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重\s?试/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '返回首页' })).toBeInTheDocument();
  });

  it('retries by clearing error state and remounting children (onError fires again)', () => {
    const onError = vi.fn();
    render(
      <PageErrorBoundary onError={onError}>
        <RenderErrorThrower />
      </PageErrorBoundary>,
    );
    // First render throws -> onError fires once and fallback UI shows.
    expect(onError).toHaveBeenCalledTimes(1);
    expect(screen.getByText('页面渲染出错')).toBeInTheDocument();
    // Click retry -> state clears, key bump forces children remount,
    // RenderErrorThrower throws again -> onError fires a second time and
    // the fallback re-renders. Verifies the retry handler runs without
    // crashing and actually re-invokes the lazy children.
    fireEvent.click(screen.getByRole('button', { name: /重\s?试/ }));
    expect(onError).toHaveBeenCalledTimes(2);
    expect(screen.getByText('页面渲染出错')).toBeInTheDocument();
  });

  it('navigates to /dashboard when "返回首页" is clicked', () => {
    render(
      <PageErrorBoundary>
        <RenderErrorThrower />
      </PageErrorBoundary>,
    );
    fireEvent.click(screen.getByRole('button', { name: '返回首页' }));
    expect(window.location.assign).toHaveBeenCalledWith('/dashboard');
  });

  it('calls onError callback when an error is caught', () => {
    const onError = vi.fn();
    render(
      <PageErrorBoundary onError={onError}>
        <RenderErrorThrower />
      </PageErrorBoundary>,
    );
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error);
    expect(onError.mock.calls[0][0].message).toMatch(/render boom/);
  });

  it('renders the custom fallback prop when provided, overriding default UI', () => {
    render(
      <PageErrorBoundary fallback={<div>custom fallback</div>}>
        <RenderErrorThrower />
      </PageErrorBoundary>,
    );
    expect(screen.getByText('custom fallback')).toBeInTheDocument();
    expect(screen.queryByText('页面渲染出错')).not.toBeInTheDocument();
  });

  it('prepends pageName to the title when provided', () => {
    render(
      <PageErrorBoundary pageName="Dashboard">
        <RenderErrorThrower />
      </PageErrorBoundary>,
    );
    expect(screen.getByText(/Dashboard · 页面渲染出错/)).toBeInTheDocument();
  });

  // C2 (spec 2026-07-30): 验证 PageErrorBoundary 捕获渲染错误时调用 reportFrontendError
  it('C2: 页面渲染错误时调用 reportFrontendError 上报 (含 boundary=page 标记)', () => {
    render(
      <PageErrorBoundary pageName="TestPage">
        <RenderErrorThrower />
      </PageErrorBoundary>,
    );
    expect(reportFrontendError).toHaveBeenCalledTimes(1);
    const callArgs = (reportFrontendError as Mock).mock.calls[0][0];
    expect(callArgs.message).toMatch(/render boom/);
    expect(callArgs.trigger).toBe('error_boundary');
    expect(callArgs.error_type).toBe('Error');
    expect(callArgs.stack).toBeDefined();
    expect(callArgs.extra).toHaveProperty('component_stack');
    expect(callArgs.extra).toHaveProperty('boundary', 'page');
  });

  it('C2: chunk 加载错误也调用 reportFrontendError 上报', () => {
    render(
      <PageErrorBoundary>
        <ChunkLoadThrower />
      </PageErrorBoundary>,
    );
    expect(reportFrontendError).toHaveBeenCalledTimes(1);
    const callArgs = (reportFrontendError as Mock).mock.calls[0][0];
    expect(callArgs.message).toMatch(/Loading chunk/);
    expect(callArgs.trigger).toBe('error_boundary');
    expect(callArgs.extra).toHaveProperty('boundary', 'page');
  });
});
