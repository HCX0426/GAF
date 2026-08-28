/**
 * QA API client unit tests (S4 multi-turn QA).
 *
 * Covers src/api/qa.ts:
 * - fetchQASessions (paginated list)
 * - fetchQASessionMessages (GET /qa/messages/by_session/?session=X)
 * - sendQAMessage (POST /qa/messages/ with {session, role, content})
 * - askQuestion (POST /qa/ask/ — new conversation + session_id continuation)
 * - markAsKnowledge (session-level knowledge toggle)
 * - deleteQASession
 * - createQASession
 * - fetchBudgetInfo
 *
 * The shared axios `client` is mocked via vi.mock so tests don't hit the
 * network. Each test asserts the correct URL, method, payload, and
 * response unwrap behavior.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockClient = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  patch: vi.fn(),
}));

vi.mock('@/api/client', () => ({
  default: mockClient,
}));

import client from '@/api/client';
import {
  fetchQASessions,
  fetchQASessionMessages,
  sendQAMessage,
  askQuestion,
  markAsKnowledge,
  deleteQASession,
  createQASession,
  fetchBudgetInfo,
} from '@/api/ai';

describe('QA API client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── fetchQASessions ───────────────────────────────────────────
  describe('fetchQASessions', () => {
    it('GETs /qa/qa-sessions/ and returns paginated results', async () => {
      const mockData = {
        count: 2,
        results: [
          { id: 1, title: 'Session 1', question: 'q1', message_count: 3 },
          { id: 2, title: 'Session 2', question: 'q2', message_count: 0 },
        ],
      };
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockData });
      const result = await fetchQASessions();
      expect(client.get).toHaveBeenCalledWith('/qa/qa-sessions/', { params: undefined });
      expect(result.count).toBe(2);
      expect(result.results).toHaveLength(2);
    });

    it('forwards pagination params', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { count: 0, results: [] } });
      await fetchQASessions({ page: 2, page_size: 10 });
      expect(client.get).toHaveBeenCalledWith('/qa/qa-sessions/', { params: { page: 2, page_size: 10 } });
    });
  });

  // ── fetchQASessionMessages ────────────────────────────────────
  describe('fetchQASessionMessages', () => {
    it('GETs /qa/messages/by_session/?session=<id> and returns message array', async () => {
      const mockMessages = [
        { id: 1, session: 5, role: 'user', content: 'hello', created_at: '2026-07-14T10:00:00Z' },
        { id: 2, session: 5, role: 'assistant', content: 'hi there', created_at: '2026-07-14T10:00:05Z' },
      ];
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockMessages });
      const result = await fetchQASessionMessages(5);
      expect(client.get).toHaveBeenCalledWith('/qa/messages/by_session/', { params: { session: 5 } });
      expect(result).toHaveLength(2);
      expect(result[0].role).toBe('user');
      expect(result[1].role).toBe('assistant');
    });

    it('returns empty array when session has no messages', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: [] });
      const result = await fetchQASessionMessages(99);
      expect(result).toEqual([]);
    });
  });

  // ── sendQAMessage ─────────────────────────────────────────────
  describe('sendQAMessage', () => {
    it('POSTs to /qa/messages/ with {session, role, content}', async () => {
      const mockMessage = { id: 10, session: 7, role: 'user', content: 'test', created_at: '2026-07-14T11:00:00Z' };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockMessage });
      const result = await sendQAMessage(7, { role: 'user', content: 'test' });
      expect(client.post).toHaveBeenCalledWith('/qa/messages/', {
        session: 7,
        role: 'user',
        content: 'test',
      });
      expect(result.id).toBe(10);
      expect(result.session).toBe(7);
    });

    it('forwards assistant role correctly', async () => {
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { id: 11, session: 7, role: 'assistant', content: 'reply', created_at: '2026-07-14T11:01:00Z' },
      });
      const result = await sendQAMessage(7, { role: 'assistant', content: 'reply' });
      expect(result.role).toBe('assistant');
    });
  });

  // ── askQuestion ───────────────────────────────────────────────
  describe('askQuestion', () => {
    it('POSTs to /qa/ask/ with question only (new conversation)', async () => {
      const mockResponse = {
        id: 1,
        title: 'What is GAF',
        question: 'What is GAF?',
        answer: 'GAF is a framework.',
        is_knowledge_entry: false,
        message_count: 2,
        last_message_at: '2026-07-14T12:00:00Z',
        created_at: '2026-07-14T12:00:00Z',
        updated_at: '2026-07-14T12:00:00Z',
      };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockResponse });
      const result = await askQuestion({ question: 'What is GAF?' });
      expect(client.post).toHaveBeenCalledWith('/qa/ask/', { question: 'What is GAF?' });
      expect(result.id).toBe(1);
      expect(result.message_count).toBe(2);
    });

    it('forwards session_id when continuing an existing conversation', async () => {
      const mockResponse = {
        id: 5,
        title: 'Existing',
        question: 'Follow up',
        answer: 'Answer',
        is_knowledge_entry: false,
        message_count: 4,
        last_message_at: '2026-07-14T12:05:00Z',
        created_at: '2026-07-14T11:00:00Z',
        updated_at: '2026-07-14T12:05:00Z',
      };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockResponse });
      const result = await askQuestion({ question: 'Follow up', session_id: 5 });
      expect(client.post).toHaveBeenCalledWith('/qa/ask/', { question: 'Follow up', session_id: 5 });
      expect(result.id).toBe(5);
      expect(result.message_count).toBe(4);
    });

    it('forwards context dict when provided', async () => {
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { id: 1, message_count: 2, last_message_at: null },
      });
      await askQuestion({ question: 'q', context: { module: 'agent' } });
      expect(client.post).toHaveBeenCalledWith('/qa/ask/', { question: 'q', context: { module: 'agent' } });
    });
  });

  // ── markAsKnowledge ───────────────────────────────────────────
  describe('markAsKnowledge', () => {
    it('POSTs to /qa/qa-sessions/<id>/mark-knowledge/ and returns updated session', async () => {
      const mockSession = { id: 3, title: 'test', is_knowledge_entry: true, message_count: 1 };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockSession });
      const result = await markAsKnowledge(3);
      expect(client.post).toHaveBeenCalledWith('/qa/qa-sessions/3/mark-knowledge/');
      expect(result.is_knowledge_entry).toBe(true);
    });
  });

  // ── deleteQASession ───────────────────────────────────────────
  describe('deleteQASession', () => {
    it('DELETEs /qa/qa-sessions/<id>/', async () => {
      (client.delete as ReturnType<typeof vi.fn>).mockResolvedValue({});
      await deleteQASession(42);
      expect(client.delete).toHaveBeenCalledWith('/qa/qa-sessions/42/');
    });
  });

  // ── createQASession ───────────────────────────────────────────
  describe('createQASession', () => {
    it('POSTs to /qa/qa-sessions/ with question + title', async () => {
      const mockSession = {
        id: 10,
        title: 'My Session',
        question: 'How to test?',
        message_count: 0,
        last_message_at: null,
      };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockSession });
      const result = await createQASession({ question: 'How to test?', title: 'My Session' });
      expect(client.post).toHaveBeenCalledWith('/qa/qa-sessions/', { question: 'How to test?', title: 'My Session' });
      expect(result.id).toBe(10);
    });
  });

  // ── fetchBudgetInfo ───────────────────────────────────────────
  describe('fetchBudgetInfo', () => {
    it('GETs /qa/qa-sessions/budget/ and returns budget info', async () => {
      const mockBudget = { budget: 1000, usage: 300, percentage: 30, status: 'normal' as const };
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockBudget });
      const result = await fetchBudgetInfo();
      expect(client.get).toHaveBeenCalledWith('/qa/qa-sessions/budget/');
      expect(result.status).toBe('normal');
      expect(result.percentage).toBe(30);
    });
  });
});
