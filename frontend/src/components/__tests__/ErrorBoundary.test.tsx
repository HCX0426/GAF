import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import ErrorBoundary from '@/components/Common/ErrorBoundary';

// C2: mock reportFrontendError 避免测试发真实网络请求
vi.mock('@/utils/reportFrontendError', () => ({
  reportFrontendError: vi.fn().mockResolvedValue(undefined),
}));

import { reportFrontendError } from '@/utils/reportFrontendError';

function ThrowError(): React.ReactElement {
  throw new Error('Test error');
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('正常子组件应正常渲染', () => {
    const { getByText } = render(
      <ErrorBoundary>
        <div>正常内容</div>
      </ErrorBoundary>,
    );
    expect(getByText('正常内容')).toBeDefined();
  });

  it('子组件抛错时应显示错误提示', () => {
    const { getByText } = render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>,
    );
    expect(getByText(/页面渲染出错/)).toBeDefined();
  });

  // C2 (spec 2026-07-30): 验证 ErrorBoundary 捕获渲染错误时调用 reportFrontendError
  it('C2: 子组件抛错时调用 reportFrontendError 上报', () => {
    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>,
    );
    expect(reportFrontendError).toHaveBeenCalledTimes(1);
    const callArgs = (reportFrontendError as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(callArgs.message).toBe('Test error');
    expect(callArgs.trigger).toBe('error_boundary');
    expect(callArgs.error_type).toBe('Error');
    expect(callArgs.stack).toBeDefined();
    expect(callArgs.extra).toHaveProperty('component_stack');
  });
});
