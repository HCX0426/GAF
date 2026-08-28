/**
 * AI API client unit tests.
 *
 * Covers src/api/ai.ts:
 * - Model evaluation CRUD (fetch / fetchById / create / run / summary / delete)
 * - LLM provider config (fetch / create / update)
 * - LLM connection test
 * - Custom skills (fetch / create / delete)
 * - Anomaly detection
 * - AI usage stats
 * - Pipeline optimization
 * - Execution log analysis
 * - Agent deep analysis
 *
 * The shared axios `client` is mocked via vi.mock so tests don't hit the
 * network. Each test asserts the correct URL, method, payload, and
 * response unwrap behavior.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the axios client — every method returns a controlled resolved value.
// vi.hoisted ensures the mock object exists when vi.mock factory runs
// (vi.mock is hoisted to top of file, before any other code).
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
  fetchModelEvaluations,
  fetchModelEvaluation,
  createModelEvaluation,
  runModelEvaluation,
  fetchModelEvaluationSummary,
  deleteModelEvaluation,
  fetchLlmProviderConfig,
  createLlmProviderConfig,
  updateLlmProviderConfig,
  testLlmConnection,
  fetchCustomSkills,
  createCustomSkill,
  deleteCustomSkill,
  detectAnomalies,
  fetchAiUsageStats,
  optimizePipeline,
  fetchExecutionAnalysis,
  analyzeExecutionWithAgent,
  fetchAgentSessionStatus,
} from '@/api/ai';

describe('AI API client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Model Evaluation ──────────────────────────────────────────
  describe('Model evaluation', () => {
    it('fetchModelEvaluations unwraps paginated results', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { count: 2, results: [{ id: 1 }, { id: 2 }] },
      });
      const result = await fetchModelEvaluations();
      expect(client.get).toHaveBeenCalledWith('/ai/model-evaluations/');
      expect(result).toEqual([{ id: 1 }, { id: 2 }]);
    });

    it('fetchModelEvaluations handles plain array response', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: [{ id: 1 }],
      });
      const result = await fetchModelEvaluations();
      expect(result).toEqual([{ id: 1 }]);
    });

    it('fetchModelEvaluations returns empty array when results missing', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
      const result = await fetchModelEvaluations();
      expect(result).toEqual([]);
    });

    it('fetchModelEvaluation retrieves a single evaluation by id', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { id: 5, name: 'eval-5' },
      });
      const result = await fetchModelEvaluation(5);
      expect(client.get).toHaveBeenCalledWith('/ai/model-evaluations/5/');
      expect(result).toEqual({ id: 5, name: 'eval-5' });
    });

    it('createModelEvaluation POSTs and returns the created evaluation', async () => {
      const payload = { name: 'New', test_cases: ['a'], models_config: [] };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { id: 10, ...payload },
      });
      const result = await createModelEvaluation(payload);
      expect(client.post).toHaveBeenCalledWith('/ai/model-evaluations/', payload);
      expect(result.id).toBe(10);
    });

    it('runModelEvaluation POSTs to /run/ subpath', async () => {
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { id: 7, status: 'completed' },
      });
      const result = await runModelEvaluation(7);
      expect(client.post).toHaveBeenCalledWith('/ai/model-evaluations/7/run/');
      expect(result.status).toBe('completed');
    });

    it('fetchModelEvaluationSummary GETs summary endpoint', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { model_stats: [] },
      });
      const result = await fetchModelEvaluationSummary(7);
      expect(client.get).toHaveBeenCalledWith('/ai/model-evaluations/7/summary/');
      expect(result).toEqual({ model_stats: [] });
    });

    it('deleteModelEvaluation DELETEs by id', async () => {
      (client.delete as ReturnType<typeof vi.fn>).mockResolvedValue({});
      await deleteModelEvaluation(42);
      expect(client.delete).toHaveBeenCalledWith('/ai/model-evaluations/42/');
    });
  });

  // ── LLM Provider Config ───────────────────────────────────────
  describe('LLM provider config', () => {
    it('fetchLlmProviderConfig GETs settings endpoint', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { id: 1, provider: 'openai' },
      });
      const result = await fetchLlmProviderConfig();
      expect(client.get).toHaveBeenCalledWith('/settings/llm-config/');
      expect(result).toEqual({ id: 1, provider: 'openai' });
    });

    it('fetchLlmProviderConfig handles array response', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: [{ id: 1 }, { id: 2 }],
      });
      const result = await fetchLlmProviderConfig();
      expect(Array.isArray(result)).toBe(true);
      expect(result).toHaveLength(2);
    });

    it('fetchLlmProviderConfig returns null when response data is null', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: null });
      const result = await fetchLlmProviderConfig();
      expect(result).toBeNull();
    });

    it('createLlmProviderConfig POSTs payload', async () => {
      const payload = { provider: 'deepseek', api_key: 'sk-x' };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { id: 1, ...payload },
      });
      const result = await createLlmProviderConfig(payload);
      expect(client.post).toHaveBeenCalledWith('/settings/llm-config/', payload);
      expect(result.id).toBe(1);
    });

    it('updateLlmProviderConfig PUTs to /{id}/', async () => {
      const payload = { api_key: 'sk-new' };
      (client.put as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { id: 3, api_key: 'sk-new' },
      });
      const result = await updateLlmProviderConfig(3, payload);
      expect(client.put).toHaveBeenCalledWith('/settings/llm-config/3/', payload);
      expect(result.id).toBe(3);
    });
  });

  // ── LLM Connection Test ───────────────────────────────────────
  describe('LLM connection test', () => {
    it('testLlmConnection POSTs to /ai/chat/', async () => {
      const payload = {
        model: 'gpt-4o-mini',
        messages: [{ role: 'user', content: 'hi' }],
      };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { content: 'hello back' },
      });
      const result = await testLlmConnection(payload);
      expect(client.post).toHaveBeenCalledWith('/ai/chat/', payload, undefined);
      expect(result.content).toBe('hello back');
    });

    it('testLlmConnection forwards timeout option', async () => {
      const payload = { model: 'm', messages: [] };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
      await testLlmConnection(payload, { timeout: 15000 });
      expect(client.post).toHaveBeenCalledWith('/ai/chat/', payload, { timeout: 15000 });
    });
  });

  // ── Custom Skills ─────────────────────────────────────────────
  describe('Custom skills', () => {
    it('fetchCustomSkills GETs list', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: [{ id: 's1', name: 'Skill 1' }],
      });
      const result = await fetchCustomSkills();
      expect(client.get).toHaveBeenCalledWith('/ai/custom-skills/');
      expect(result).toEqual([{ id: 's1', name: 'Skill 1' }]);
    });

    it('fetchCustomSkills handles paginated response', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { results: [{ id: 's1' }] },
      });
      const result = await fetchCustomSkills();
      expect(result).toEqual({ results: [{ id: 's1' }] });
    });

    it('createCustomSkill POSTs skill data', async () => {
      const skillData = { id: 'new', name: 'New', yaml_content: 'x' };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { ...skillData, created_at: '2026-01-01' },
      });
      const result = await createCustomSkill(skillData);
      expect(client.post).toHaveBeenCalledWith('/ai/custom-skills/', skillData);
      expect(result.created_at).toBe('2026-01-01');
    });

    it('deleteCustomSkill DELETEs by id', async () => {
      (client.delete as ReturnType<typeof vi.fn>).mockResolvedValue({});
      await deleteCustomSkill('abc');
      expect(client.delete).toHaveBeenCalledWith('/ai/custom-skills/abc/');
    });
  });

  // ── Anomaly Detection ─────────────────────────────────────────
  describe('Anomaly detection', () => {
    it('detectAnomalies POSTs payload', async () => {
      const payload = { days: 7, min_occurrences: 2 };
      const mockResult = {
        patterns: [{ pattern_text: 'timeout', occurrence_count: 3 }],
        summary: 'found 1 pattern',
        llm_analysis: null,
        stats: { failed_count: 5, total_count: 10, failure_rate: 50, unique_errors: 3 },
        total_analyzed: 5,
      };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockResult });
      const result = await detectAnomalies(payload);
      expect(client.post).toHaveBeenCalledWith('/ai/anomaly-detection/', payload);
      expect(result.patterns).toHaveLength(1);
      expect(result.stats.failure_rate).toBe(50);
    });
  });

  // ── AI Usage Stats ────────────────────────────────────────────
  describe('AI usage stats', () => {
    it('fetchAiUsageStats GETs with optional days param', async () => {
      const mockStats = { total_requests: 100, total_tokens: 5000 };
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockStats });
      const result = await fetchAiUsageStats({ days: 30 });
      expect(client.get).toHaveBeenCalledWith('/ai/usage-stats/', { params: { days: 30 } });
      expect(result.total_requests).toBe(100);
    });

    it('fetchAiUsageStats works without params', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
      const result = await fetchAiUsageStats();
      expect(client.get).toHaveBeenCalledWith('/ai/usage-stats/', { params: undefined });
      expect(result).toEqual({});
    });

    it('fetchAiUsageStats returns empty object when data is null', async () => {
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: null });
      const result = await fetchAiUsageStats();
      expect(result).toEqual({});
    });
  });

  // ── Pipeline Optimization ─────────────────────────────────────
  describe('Pipeline optimization', () => {
    it('optimizePipeline POSTs pipeline_id and model', async () => {
      const payload = { pipeline_id: '5', model: 'gpt-4o-mini' };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { suggestions: [] },
      });
      const result = await optimizePipeline(payload);
      expect(client.post).toHaveBeenCalledWith('/ai/optimize-pipeline/', payload);
      expect(result).toEqual({ suggestions: [] });
    });
  });

  // ── Execution Log Analysis ────────────────────────────────────
  describe('Execution log analysis', () => {
    it('fetchExecutionAnalysis GETs /executions/{id}/analysis', async () => {
      const mockResult = {
        steps: [{ name: 'step1', status: 'success', duration_ms: 100 }],
        summary: 'OK',
        suggestions: [],
      };
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockResult });
      const result = await fetchExecutionAnalysis('42');
      expect(client.get).toHaveBeenCalledWith('/executions/42/analysis');
      expect(result.steps).toHaveLength(1);
    });
  });

  // ── Agent Deep Analysis ───────────────────────────────────────
  describe('Agent deep analysis', () => {
    it('analyzeExecutionWithAgent POSTs to /ai/agent/analyze/ and returns pending session', async () => {
      const mockDispatch = {
        session_id: 1,
        status: 'pending',
        message: 'Analysis dispatched. Poll GET /api/v2/ai/agent/sessions/1/ for results.',
      };
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockDispatch });
      const result = await analyzeExecutionWithAgent('42');
      expect(client.post).toHaveBeenCalledWith('/ai/agent/analyze/', { execution_id: 42 });
      expect(result.session_id).toBe(1);
      expect(result.status).toBe('pending');
    });

    it('analyzeExecutionWithAgent accepts numeric executionId', async () => {
      (client.post as ReturnType<typeof vi.fn>).mockResolvedValue({
        data: { session_id: 1, status: 'pending' },
      });
      await analyzeExecutionWithAgent(99);
      expect(client.post).toHaveBeenCalledWith('/ai/agent/analyze/', { execution_id: 99 });
    });

    it('fetchAgentSessionStatus GETs /ai/agent/sessions/<id>/', async () => {
      const mockResult = {
        session_id: 1,
        status: 'completed' as const,
        model_used: 'deepseek-v3',
        reasoning_steps: [],
        summary: 'OK',
        suggestions: [],
        total_tokens: 100,
        error: null,
      };
      (client.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: mockResult });
      const result = await fetchAgentSessionStatus(1);
      expect(client.get).toHaveBeenCalledWith('/ai/agent/sessions/1/');
      expect(result.status).toBe('completed');
    });
  });
});
