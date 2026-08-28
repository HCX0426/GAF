/**
 * ExecutionMonitorPanel onStepClick 跳转失败节点截图 (N192 B7 P1).
 *
 * 渲染 ExecutionMonitorPanel 直接测试不可行 (依赖 useScreenshotStream /
 * useWebSocket / wsClient / App.useApp 等大量 provider), 因此拆为两层契约测试:
 *   1. StepProgressBar 行为契约: 点击 failed/success 步骤应触发 onStepClick,
 *      点击 pending 不触发 (spec issue: 原代码 isCompleted 守卫排除了 failed,
 *      与 "跳转失败节点截图" 矛盾)
 *   2. fetchExecutionReplay API 契约: 调用 /tasks/task-executions/{id}/replay/
 *      并返回含 stepIndex 字段的 frames, 供 handleStepClick 按 step.index 定位帧
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StepProgressBar, type StepInfo } from '@/components/Pipeline/StepProgressBar';

// Mock the API client — executions.ts does `import client from './client'`
// so we mock the default export with a get stub (fetchExecutionReplay uses get).
vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
  },
}));

import client from '@/api/client';
import { fetchExecutionReplay } from '@/api/executions';

describe('StepProgressBar onStepClick — failed 步骤可点击 (N192 B7 P1)', () => {
  it('triggers onStepClick when clicking a failed step', () => {
    const onStepClick = vi.fn();
    const steps: StepInfo[] = [{ index: 0, name: 'Step 1', status: 'failed', error_message: 'template not found' }];
    render(<StepProgressBar steps={steps} onStepClick={onStepClick} />);
    // 点击步骤名区域 (onClick 挂在包裹步骤名的 div 上)
    fireEvent.click(screen.getByText(/Step 1/));
    expect(onStepClick).toHaveBeenCalledTimes(1);
    expect(onStepClick).toHaveBeenCalledWith(expect.objectContaining({ status: 'failed', index: 0 }));
  });

  it('triggers onStepClick when clicking a success step (backward compat)', () => {
    const onStepClick = vi.fn();
    const steps: StepInfo[] = [{ index: 0, name: 'Step 1', status: 'success', duration: 100 }];
    render(<StepProgressBar steps={steps} onStepClick={onStepClick} />);
    fireEvent.click(screen.getByText(/Step 1/));
    expect(onStepClick).toHaveBeenCalledTimes(1);
    expect(onStepClick).toHaveBeenCalledWith(expect.objectContaining({ status: 'success' }));
  });

  it('does NOT trigger onStepClick for pending steps', () => {
    const onStepClick = vi.fn();
    const steps: StepInfo[] = [{ index: 0, name: 'Step 1', status: 'pending' }];
    render(<StepProgressBar steps={steps} onStepClick={onStepClick} />);
    fireEvent.click(screen.getByText(/Step 1/));
    expect(onStepClick).not.toHaveBeenCalled();
  });

  it('does NOT trigger onStepClick for running steps', () => {
    const onStepClick = vi.fn();
    const steps: StepInfo[] = [{ index: 0, name: 'Step 1', status: 'running' }];
    render(<StepProgressBar steps={steps} onStepClick={onStepClick} />);
    fireEvent.click(screen.getByText(/Step 1/));
    expect(onStepClick).not.toHaveBeenCalled();
  });

  it('does not render clickable cursor when onStepClick absent', () => {
    const steps: StepInfo[] = [{ index: 0, name: 'Step 1', status: 'failed' }];
    render(<StepProgressBar steps={steps} />);
    // 不传 onStepClick 时点击不应抛错, 也无回调可触发 (此用例仅验证不崩溃)
    fireEvent.click(screen.getByText(/Step 1/));
    // 无断言异常即通过 — 验证 guard 不依赖 onStepClick 存在
  });
});

describe('fetchExecutionReplay API contract (N192 B7 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns frames with stepIndex field and calls correct endpoint', async () => {
    const mockFrames = [
      { index: 0, imageBase64: 'abc', timestamp: '2026-07-27T10:00:00Z', stepIndex: 0 },
      { index: 1, imageBase64: 'def', timestamp: '2026-07-27T10:00:05Z', stepIndex: 1 },
    ];
    (client.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { frames: mockFrames, steps: [] },
    });

    const result = await fetchExecutionReplay(123);

    expect(client.get).toHaveBeenCalledWith('/tasks/task-executions/123/replay/');
    expect(result.frames).toHaveLength(2);
    expect(result.frames?.[0].stepIndex).toBe(0);
    expect(result.frames?.[1].stepIndex).toBe(1);
  });

  it('returns empty frames array gracefully (in-progress execution may have no frames)', async () => {
    (client.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { frames: [], steps: [] },
    });

    const result = await fetchExecutionReplay(456);

    expect(result.frames).toEqual([]);
    expect(result.frames).toHaveLength(0);
  });

  it('handles missing frames field as undefined', async () => {
    (client.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { steps: [] },
    });

    const result = await fetchExecutionReplay(789);

    expect(result.frames).toBeUndefined();
  });
});
