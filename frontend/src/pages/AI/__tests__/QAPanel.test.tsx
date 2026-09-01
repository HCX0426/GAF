/**
 * QAPanel smoke tests (AI tab, Phase 3 QA model selection).
 * Covers: model dropdown renders active provider's models, send carries the
 * selected model to askQuestion.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { QAPanel } from '@/pages/AI/QAPanel';

const mockAi = vi.hoisted(() => ({
  fetchQASessions: vi.fn().mockResolvedValue({ results: [] }),
  fetchQASessionMessages: vi.fn().mockResolvedValue([]),
  askQuestion: vi.fn().mockResolvedValue({ id: 1, question: 'hi' }),
  markAsKnowledge: vi.fn(),
  deleteQASession: vi.fn(),
  fetchLlmProviderConfig: vi.fn().mockResolvedValue([
    {
      id: 1,
      provider: 'openai',
      default_model: 'deepseek-ai/DeepSeek-V4-Flash',
      available_models: ['deepseek-ai/DeepSeek-V4-Flash', 'gpt-4o-mini'],
      is_active: true,
    },
  ]),
}));

vi.mock('@/api/ai', () => mockAi);

import { askQuestion, fetchLlmProviderConfig } from '@/api/ai';

beforeEach(() => {
  vi.clearAllMocks();
});

// jsdom does not implement scrollIntoView; polyfill for the auto-scroll effect.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <AntApp>
        <QAPanel />
      </AntApp>
    </MemoryRouter>,
  );
}

describe('QAPanel', () => {
  it('加载激活 provider 的模型下拉', async () => {
    renderPage();
    await waitFor(() => {
      expect(fetchLlmProviderConfig).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByText('deepseek-ai/DeepSeek-V4-Flash (openai)')).toBeDefined();
    });
  });

  it('发送问题携带所选模型', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('deepseek-ai/DeepSeek-V4-Flash (openai)')).toBeDefined();
    });
    // Input area placeholder
    const textarea = screen.getByPlaceholderText('输入你的问题…（支持多轮追问，自动携带上下文）');
    fireEvent.change(textarea, { target: { value: '如何修复超时' } });
    fireEvent.click(screen.getByText('发送'));
    await waitFor(() => {
      expect(askQuestion).toHaveBeenCalledWith(
        expect.objectContaining({
          question: '如何修复超时',
          model: 'deepseek-ai/DeepSeek-V4-Flash',
        }),
      );
    });
  });
});
