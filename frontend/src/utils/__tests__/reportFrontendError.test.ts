/**
 * C3 spec 2026-07-30: reportFrontendError 单测。
 *
 * 验证上报 payload 自动附加 trace_id (从 sessionStorage) + page_slug (从
 * window.location.pathname), 让 backend 按 page_slug 归集到 console.jsonl,
 * AI 调试时能 grep trace_id 串联三端日志。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { MockInstance } from 'vitest';

// mock axios 避免 vitest 发真实网络请求
vi.mock('axios', () => ({
  default: {
    post: vi.fn().mockResolvedValue({ status: 204 }),
  },
}));
import axios from 'axios';

// mock pageSlug + traceId 避免依赖 jsdom window.location 状态
vi.mock('@/utils/pageSlug', () => ({
  getPageSlug: vi.fn().mockReturnValue('dashboard'),
}));
vi.mock('@/utils/traceId', () => ({
  getLastTraceId: vi.fn().mockReturnValue('11111111-2222-4333-8444-555555555555'),
  setLastTraceId: vi.fn(),
  generateTraceId: vi.fn().mockReturnValue('11111111-2222-4333-8444-555555555555'),
}));

import { reportFrontendError } from '@/utils/reportFrontendError';
import { getPageSlug } from '@/utils/pageSlug';
import { getLastTraceId } from '@/utils/traceId';

describe('reportFrontendError — C3 trace_id + page_slug 自动附加', () => {
  let axiosPostMock: ReturnType<typeof vi.fn>;
  let consoleWarnSpy: MockInstance;

  beforeEach(() => {
    axiosPostMock = axios.post as unknown as ReturnType<typeof vi.fn>;
    axiosPostMock.mockClear();
    axiosPostMock.mockResolvedValue({ status: 204 });
    (getPageSlug as unknown as ReturnType<typeof vi.fn>).mockReturnValue('dashboard');
    (getLastTraceId as unknown as ReturnType<typeof vi.fn>).mockReturnValue('11111111-2222-4333-8444-555555555555');
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    sessionStorage.clear();
  });

  afterEach(() => {
    consoleWarnSpy.mockRestore();
  });

  it('C3: 上报 payload 自动附带 trace_id + page_slug', async () => {
    await reportFrontendError({
      message: 'Test error',
      trigger: 'window.onerror',
    });

    expect(axiosPostMock).toHaveBeenCalledTimes(1);
    const [, payload] = axiosPostMock.mock.calls[0];
    expect(payload.trace_id).toBe('11111111-2222-4333-8444-555555555555');
    expect(payload.page_slug).toBe('dashboard');
    // 其他必填字段仍存在
    expect(payload.message).toBe('Test error');
    expect(payload.trigger).toBe('window.onerror');
    expect(payload.page_url).toBeDefined();
    expect(payload.user_agent).toBeDefined();
    expect(payload.session_id).toBeDefined();
  });

  it('C3: trace_id 为空时 (无 HTTP 请求上下文) payload.trace_id = ""', async () => {
    (getLastTraceId as unknown as ReturnType<typeof vi.fn>).mockReturnValue('');

    await reportFrontendError({
      message: 'Render crash before any request',
      trigger: 'error_boundary',
    });

    const [, payload] = axiosPostMock.mock.calls[0];
    // backend 接收空 trace_id 仍会落盘 (AI 调试时按 "trace_id 为空" 过滤)
    expect(payload.trace_id).toBe('');
    expect(payload.page_slug).toBe('dashboard');
  });

  it('C3: page_slug 跟随当前页面 ( getPageSlug 实时调用)', async () => {
    (getPageSlug as unknown as ReturnType<typeof vi.fn>).mockReturnValue('tasks_pipeline');

    await reportFrontendError({
      message: 'Page-specific error',
      trigger: 'unhandledrejection',
    });

    const [, payload] = axiosPostMock.mock.calls[0];
    expect(payload.page_slug).toBe('tasks_pipeline');
  });

  it('C3: 调用方不应手动传 trace_id / page_slug (会被覆盖)', async () => {
    // 设计意图: reportFrontendError 在出错瞬间统一采集, caller 不应传
    // 这里验证即使 caller 传了, 也以运行时采集的为准
    await reportFrontendError({
      message: 'x',
      trigger: 'window.onerror',
      // trace_id 和 page_slug 是可选字段, 调用方可传但会被运行时覆盖
      trace_id: 'stale-trace',
      page_slug: 'stale-slug',
    });

    const [, payload] = axiosPostMock.mock.calls[0];
    expect(payload.trace_id).toBe('11111111-2222-4333-8444-555555555555');
    expect(payload.page_slug).toBe('dashboard');
  });

  it('C3: 上报 URL 含 /logs/frontend-errors/ 路径', async () => {
    // 用唯一 message 避免 dedup cache 命中前一个测试的报告
    await reportFrontendError({ message: 'unique-url-test-message', trigger: 'window.onerror' });

    const [url] = axiosPostMock.mock.calls[0];
    expect(url).toContain('/logs/frontend-errors/');
  });
});
