/**
 * spec 2026-08-31-ai-tab-agent-learning-spec Phase 1: AiConfigPage 组件测试.
 * 覆盖: Provider 卡片列表渲染 / 激活标记 / 添加弹窗 / 设为激活 / 连接测试 / 激活项禁删.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { AiConfigPage } from '@/pages/AI/AiConfigPage';

const mockProviders = vi.hoisted(() => [
  {
    id: 1,
    provider: 'openai',
    api_key_masked: 'sk-***ab12',
    api_base: 'https://api.openai.com/v1',
    default_model: 'gpt-4o-mini',
    temperature: 0.7,
    max_tokens: 4096,
    is_active: true,
  },
  {
    id: 2,
    provider: 'deepseek',
    api_key_masked: 'sk-***cd34',
    api_base: 'https://api.deepseek.com/v1',
    default_model: 'deepseek-chat',
    temperature: 0.3,
    max_tokens: 4096,
    is_active: false,
  },
]);

const mockAiApi = vi.hoisted(() => ({
  fetchLlmProviderConfig: vi.fn().mockResolvedValue(mockProviders),
  createLlmProviderConfig: vi.fn(),
  updateLlmProviderConfig: vi.fn(),
  deleteLlmProviderConfig: vi.fn(),
  setActiveLlmProvider: vi.fn().mockResolvedValue(mockProviders[1]),
  testLlmConnection: vi.fn().mockResolvedValue({ content: 'OK' }),
  testLlmProvider: vi.fn().mockResolvedValue({ success: true, latency_ms: 120 }),
}));

vi.mock('@/api/ai', () => mockAiApi);

import {
  fetchLlmProviderConfig,
  setActiveLlmProvider,
  testLlmConnection,
  testLlmProvider,
  deleteLlmProviderConfig,
} from '@/api/ai';

beforeEach(() => {
  vi.clearAllMocks();
  fetchLlmProviderConfig.mockResolvedValue(mockProviders);
});

function renderPage() {
  return render(
    <MemoryRouter>
      <AntApp>
        <AiConfigPage />
      </AntApp>
    </MemoryRouter>,
  );
}

describe('AiConfigPage', () => {
  it('渲染 Provider 卡片列表并标记激活/未激活', async () => {
    renderPage();
    await waitFor(() => {
      expect(fetchLlmProviderConfig).toHaveBeenCalled();
      expect(screen.getByText('OpenAI')).toBeDefined();
      expect(screen.getByText('DeepSeek')).toBeDefined();
    });
    await waitFor(() => {
      expect(screen.getByText('已激活')).toBeDefined();
      expect(screen.getByText('未激活')).toBeDefined();
    });
  });

  it('点击"添加 Provider"打开编辑弹窗', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeDefined();
    });
    fireEvent.click(screen.getByText('添加 Provider'));
    // 弹窗内才有的表单标签
    await waitFor(() => {
      expect(screen.getByText('默认模型')).toBeDefined();
    });
  });

  it('点击"设为激活"调用 setActiveLlmProvider 并刷新列表', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('DeepSeek')).toBeDefined();
    });
    fireEvent.click(screen.getByText('设为激活'));
    await waitFor(() => {
      expect(setActiveLlmProvider).toHaveBeenCalledWith(2);
      // 激活后刷新列表
      expect(fetchLlmProviderConfig.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('点击"测试连接"用激活 provider 的模型调用 testLlmConnection', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('测试连接')).toBeDefined();
    });
    fireEvent.click(screen.getByText('测试连接'));
    await waitFor(() => {
      expect(testLlmConnection).toHaveBeenCalledWith(
        expect.objectContaining({ model: 'gpt-4o-mini' }),
        expect.objectContaining({ timeout: 15000 }),
      );
    });
  });

  it('每张 provider 卡片的"测试"按钮调用 testLlmProvider(id)', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeDefined();
    });
    // 卡片级测试按钮（与顶部横幅的"测试连接"区分开）
    const testBtns = screen.getAllByRole('button');
    const cardTest = testBtns.find((b) => (b as HTMLButtonElement).textContent === '测试');
    expect(cardTest).toBeDefined();
    fireEvent.click(cardTest as HTMLElement);
    await waitFor(() => {
      expect(testLlmProvider).toHaveBeenCalledWith(1);
    });
  });

  it('编辑弹窗展示模型列表并回填 available_models', async () => {
    // 给第一个 provider 加 available_models
    fetchLlmProviderConfig.mockResolvedValueOnce([
      { ...mockProviders[0], available_models: ['gpt-4o-mini', 'gpt-4o'] },
      mockProviders[1],
    ]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeDefined();
    });
    fireEvent.click(screen.getAllByText('编辑')[0]);
    await waitFor(() => {
      expect(screen.getByText('模型列表')).toBeDefined();
    });
  });

  it('激活 provider 的删除按钮禁用', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('OpenAI')).toBeDefined();
    });
    // 两张卡各有一个 danger 删除按钮；激活项 (openai) 的禁用
    const deleteBtns = screen
      .getAllByRole('button')
      .filter((b) => (b as HTMLButtonElement).className.includes('ant-btn-dangerous'));
    expect(deleteBtns.length).toBe(2);
    expect((deleteBtns[0] as HTMLButtonElement).disabled).toBe(true);
    expect((deleteBtns[1] as HTMLButtonElement).disabled).toBe(false);
    expect(deleteLlmProviderConfig).not.toHaveBeenCalled();
  });
});
