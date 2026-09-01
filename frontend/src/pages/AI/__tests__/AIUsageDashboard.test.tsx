/**
 * AIUsageDashboard smoke tests (AI tab usage).
 * Covers: by_model -> model_distribution mapping (key-contract fix),
 * agent evaluation card rendering.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { AIUsageDashboard } from '@/pages/AI/AIUsageDashboard';

const mockAi = vi.hoisted(() => ({
  fetchAiUsageStats: vi.fn().mockResolvedValue({
    total_requests: 5,
    success_rate: 100,
    total_tokens: 9893,
    cost_estimate_usd: 0.0204,
    by_model: [
      { model: 'deepseek-ai/DeepSeek-V4-Flash', requests: 5, tokens: 9893, cost_usd: 0.0204 },
    ],
    daily_trend: [{ date: '2026-09-01', requests: 5, tokens: 9893 }],
  }),
  fetchAgentEvaluation: vi.fn().mockResolvedValue({
    window_days: 30,
    total_sessions: 2,
    completed_sessions: 2,
    failed_sessions: 0,
    completion_rate: 1,
    avg_latency_seconds: 81,
    avg_tool_calls_per_session: 9.5,
    total_tokens: 100,
    avg_tokens: 50,
    total_cost: 0.01,
    sessions_with_tools: 1,
    tool_steps: 2,
  }),
}));

vi.mock('@/api/ai', () => mockAi);

import { fetchAiUsageStats, fetchAgentEvaluation } from '@/api/ai';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AIUsageDashboard', () => {
  it('渲染成本与模型分布（by_model 修复后非空）', async () => {
    render(
      <MemoryRouter>
        <AntApp>
          <AIUsageDashboard />
        </AntApp>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(fetchAiUsageStats).toHaveBeenCalled();
    });
    // 成本键名修复: cost_estimate_usd -> estimated_cost
    await waitFor(() => {
      expect(screen.getByText('$0.02')).toBeDefined();
    });
    // by_model -> model_distribution 映射后"暂无数据"空态不再出现
    await waitFor(() => {
      expect(screen.queryByText('暂无数据')).toBeNull();
    });
  });

  it('渲染 Agent 评测卡片', async () => {
    render(
      <MemoryRouter>
        <AntApp>
          <AIUsageDashboard />
        </AntApp>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(fetchAgentEvaluation).toHaveBeenCalled();
    });
    await waitFor(() => {
      // Agent 分析结果区块渲染（标题存在；Statistic 值被拆成 int/decimal 段，用标题断言）
      expect(screen.getByText('Agent 分析结果')).toBeDefined();
    });
  });
});
