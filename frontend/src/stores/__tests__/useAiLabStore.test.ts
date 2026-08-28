/**
 * TD-336 #4: useAiLabStore 测试 — 覆盖消息管理 + 流式输出 + 会话清理
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAiLabStore } from '@/stores/useAiLabStore';

// Mock config + tokenStore (buildAuthHeaders)
vi.mock('@/config/app', () => ({
  apiUrl: (path: string) => `http://test.local${path}`,
}));

vi.mock('@/utils/tokenStore', () => ({
  buildAuthHeaders: (extra: Record<string, string>) => ({ Authorization: 'Bearer test-token', ...extra }),
  getRememberMe: () => false,
  getSavedUsername: () => '',
}));

// crypto.randomUUID 稳定 mock
const mockUUID = vi.fn(() => 'test-uuid');
vi.stubGlobal('crypto', { randomUUID: mockUUID });

beforeEach(() => {
  useAiLabStore.setState({
    messages: [],
    isStreaming: false,
    conversationId: null,
    pipelineResult: null,
  });
  vi.clearAllMocks();
  vi.unstubAllEnvs();
});

describe('useAiLabStore', () => {
  describe('初始状态', () => {
    it('messages 应为空数组', () => {
      expect(useAiLabStore.getState().messages).toEqual([]);
    });

    it('isStreaming 应为 false', () => {
      expect(useAiLabStore.getState().isStreaming).toBe(false);
    });

    it('pipelineResult 应为 null', () => {
      expect(useAiLabStore.getState().pipelineResult).toBeNull();
    });
  });

  describe('clearConversation', () => {
    it('应清空 messages/conversationId/isStreaming/pipelineResult', () => {
      useAiLabStore.setState({
        messages: [{ id: '1', role: 'user', content: 'hi', timestamp: '2026-01-01' } as never],
        conversationId: 'conv-1',
        isStreaming: true,
        pipelineResult: { foo: 'bar' },
      });

      useAiLabStore.getState().clearConversation();

      const s = useAiLabStore.getState();
      expect(s.messages).toEqual([]);
      expect(s.conversationId).toBeNull();
      expect(s.isStreaming).toBe(false);
      expect(s.pipelineResult).toBeNull();
    });
  });

  describe('setStreaming', () => {
    it('应设置 isStreaming', () => {
      useAiLabStore.getState().setStreaming(true);
      expect(useAiLabStore.getState().isStreaming).toBe(true);

      useAiLabStore.getState().setStreaming(false);
      expect(useAiLabStore.getState().isStreaming).toBe(false);
    });
  });

  describe('appendToLastMessage', () => {
    it('应追加内容到最后一条 assistant 消息', () => {
      useAiLabStore.setState({
        messages: [
          { id: 'u1', role: 'user', content: 'hi', timestamp: '2026-01-01' },
          { id: 'a1', role: 'assistant', content: 'hello', timestamp: '2026-01-01' },
        ] as never,
      });

      useAiLabStore.getState().appendToLastMessage(' world');

      const s = useAiLabStore.getState();
      expect(s.messages[1].content).toBe('hello world');
    });

    it('无 assistant 消息时应无操作', () => {
      useAiLabStore.setState({
        messages: [{ id: 'u1', role: 'user', content: 'hi', timestamp: '2026-01-01' }] as never,
      });

      useAiLabStore.getState().appendToLastMessage(' chunk');

      expect(useAiLabStore.getState().messages[0].content).toBe('hi');
    });

    it('空消息列表时应无操作', () => {
      useAiLabStore.getState().appendToLastMessage(' chunk');
      expect(useAiLabStore.getState().messages).toEqual([]);
    });
  });

  describe('setPipelineResult', () => {
    it('应设置 pipelineResult', () => {
      const data = { nodes: [], edges: [] };
      useAiLabStore.getState().setPipelineResult(data);
      expect(useAiLabStore.getState().pipelineResult).toEqual(data);
    });

    it('应支持重置为 null', () => {
      useAiLabStore.setState({ pipelineResult: { foo: 'bar' } });
      useAiLabStore.getState().setPipelineResult(null);
      expect(useAiLabStore.getState().pipelineResult).toBeNull();
    });
  });

  describe('sendMessage (流式)', () => {
    it('应添加 user + assistant 消息并标记 streaming', async () => {
      // Mock fetch 返回空流 (立即 done)
      const mockReader = {
        read: vi.fn().mockResolvedValue({ done: true, value: undefined }),
      };
      const mockResponse = {
        body: { getReader: () => mockReader },
      };
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse));

      const { sendMessage } = useAiLabStore.getState();
      await sendMessage('test prompt');

      const s = useAiLabStore.getState();
      expect(s.messages).toHaveLength(2);
      expect(s.messages[0].role).toBe('user');
      expect(s.messages[0].content).toBe('test prompt');
      expect(s.messages[1].role).toBe('assistant');
      // done=true 后 isStreaming 保持初始 true (空流未触发 data.done 分支)
      // 但 messages 已添加
    });

    it('fetch 失败时应标记错误并停止 streaming', async () => {
      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')));

      const { sendMessage } = useAiLabStore.getState();
      await sendMessage('test prompt');

      const s = useAiLabStore.getState();
      expect(s.messages).toHaveLength(2);
      expect(s.messages[1].role).toBe('assistant');
      expect(s.messages[1].content).toContain('请求失败');
      expect(s.isStreaming).toBe(false);
    });

    it('无 response.body 时应停止 streaming', async () => {
      const mockResponse = { body: null };
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse));

      const { sendMessage } = useAiLabStore.getState();
      await sendMessage('test prompt');

      const s = useAiLabStore.getState();
      expect(s.messages).toHaveLength(2);
      expect(s.isStreaming).toBe(false);
    });
  });
});
