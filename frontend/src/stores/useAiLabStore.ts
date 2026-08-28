/**
 * AI Lab status management Store
 * management AI to conversation message list, streaming output status, session ID
 */
import { create } from 'zustand';
import type { AIMessage } from '@/types/models';
import { apiUrl } from '@/config/app';
import { buildAuthHeaders } from '@/utils/tokenStore';

interface AiLabState {
  messages: AIMessage[];
  isStreaming: boolean;
  conversationId: string | null;
  sendMessage: (content: string) => Promise<void>;
  clearConversation: () => void;
  setStreaming: (streaming: boolean) => void;
  appendToLastMessage: (chunk: string) => void;
  setPipelineResult: (pipelineData: Record<string, unknown> | null) => void;
  pipelineResult: Record<string, unknown> | null;
}

export const useAiLabStore = create<AiLabState>((set) => ({
  messages: [],
  isStreaming: false,
  conversationId: null,
  pipelineResult: null,

  sendMessage: async (content: string) => {
    const userMessage: AIMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };
    const assistantId = crypto.randomUUID();
    const assistantMessage: AIMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, userMessage, assistantMessage],
      isStreaming: true,
      pipelineResult: null,
    }));

    try {
      // M22: use shared buildAuthHeaders utility.
      const headers = buildAuthHeaders({ 'Content-Type': 'application/json' });
      const response = await fetch(apiUrl('/ai/generate-pipeline-stream/'), {
        method: 'POST',
        headers,
        body: JSON.stringify({ description: content }),
      });

      const reader = response.body?.getReader();
      if (!reader) {
        set({ isStreaming: false });
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.chunk) {
                fullContent += data.chunk;
                set((state) => ({
                  messages: state.messages.map((m) => (m.id === assistantId ? { ...m, content: fullContent } : m)),
                }));
              }
              if (data.done) {
                set((state) => ({
                  messages: state.messages.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: data.raw_content || fullContent, metadata: { pipelineData: data.graph_data } }
                      : m,
                  ),
                  pipelineResult: data.graph_data,
                  isStreaming: false,
                }));
              }
              if (data.error) {
                set((state) => ({
                  messages: state.messages.map((m) =>
                    m.id === assistantId ? { ...m, content: `错误: ${data.error}` } : m,
                  ),
                  isStreaming: false,
                }));
              }
            } catch {
              // skip malformed
            }
          }
        }
      }
    } catch (e) {
      set((state) => ({
        messages: state.messages.map((m) => (m.id === assistantId ? { ...m, content: `请求失败: ${String(e)}` } : m)),
        isStreaming: false,
      }));
    }
  },

  clearConversation: () => {
    set({ messages: [], conversationId: null, isStreaming: false, pipelineResult: null });
  },

  setStreaming: (streaming: boolean) => set({ isStreaming: streaming }),

  appendToLastMessage: (chunk: string) => {
    set((state) => {
      const msgs = [...state.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + chunk };
      }
      return { messages: msgs };
    });
  },

  setPipelineResult: (pipelineData) => set({ pipelineResult: pipelineData }),
}));
