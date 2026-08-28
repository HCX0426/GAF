/**
 * StepProgressBar error_message 渲染测试 (N192 B6 P0).
 *
 * 验证:
 * - failed 状态的 step 应渲染 error_message (红色文字)
 * - success/running/pending 状态的 step 不应渲染 error_message
 * - error_message 为空时不渲染
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StepProgressBar, type StepInfo } from '@/components/Pipeline/StepProgressBar';

describe('StepProgressBar error_message 渲染', () => {
  it('renders error_message when step is failed', () => {
    const steps: StepInfo[] = [
      {
        index: 0,
        name: 'Step 1',
        status: 'failed',
        duration: 1500,
        error_message: '模板未找到: tpl_001',
      },
    ];
    render(<StepProgressBar steps={steps} />);
    expect(screen.getByText(/模板未找到/)).toBeInTheDocument();
  });

  it('does not render error_message for success steps', () => {
    const steps: StepInfo[] = [
      {
        index: 0,
        name: 'Step 1',
        status: 'success',
        duration: 100,
        error_message: 'should not show',
      },
    ];
    render(<StepProgressBar steps={steps} />);
    expect(screen.queryByText(/should not show/)).toBeNull();
  });

  it('does not render error_message when undefined', () => {
    const steps: StepInfo[] = [
      {
        index: 0,
        name: 'Step 1',
        status: 'failed',
        duration: 500,
        // error_message 未设置
      },
    ];
    render(<StepProgressBar steps={steps} />);
    // 应该不报错, 只是没渲染 error_message 行
    expect(screen.getByText(/Step 1/)).toBeInTheDocument();
  });

  it('renders long error_message with word break', () => {
    const longMsg = 'a'.repeat(200);
    const steps: StepInfo[] = [
      {
        index: 0,
        name: 'Step 1',
        status: 'failed',
        duration: 500,
        error_message: longMsg,
      },
    ];
    render(<StepProgressBar steps={steps} />);
    // 长消息也应该被渲染 (wordBreak: break-word 防止溢出)
    expect(screen.getByText(new RegExp(longMsg.slice(0, 50)))).toBeInTheDocument();
  });
});
