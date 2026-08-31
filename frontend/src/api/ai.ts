/**
 * AI model evaluation API client (P-031).
 */
import client from './client';
import type {
  CreateModelEvaluationPayload,
  ModelEvaluation,
  ModelEvaluationSummary,
  PaginatedResponse,
  QASession,
  QAAskRequest,
  QAAskResponse,
} from '@/types/models';

/** List current user's model evaluations */
export async function fetchModelEvaluations(): Promise<ModelEvaluation[]> {
  const res = await client.get<PaginatedResponse<ModelEvaluation>>('/ai/model-evaluations/');
  // DRF default pagination returns { count, next, previous, results }
  if (Array.isArray(res.data)) return res.data;
  return res.data.results ?? [];
}

/** Retrieve a single evaluation with all results */
export async function fetchModelEvaluation(id: number): Promise<ModelEvaluation> {
  const res = await client.get<ModelEvaluation>(`/ai/model-evaluations/${id}/`);
  return res.data;
}

/** Create a new evaluation (auto-runs synchronously and returns completed result) */
export async function createModelEvaluation(payload: CreateModelEvaluationPayload): Promise<ModelEvaluation> {
  const res = await client.post<ModelEvaluation>('/ai/model-evaluations/', payload);
  return res.data;
}

/** Re-run an existing evaluation (clears old results) */
export async function runModelEvaluation(id: number): Promise<ModelEvaluation> {
  const res = await client.post<ModelEvaluation>(`/ai/model-evaluations/${id}/run/`);
  return res.data;
}

/** Get aggregated summary per model (sorted by avg_score descending) */
export async function fetchModelEvaluationSummary(id: number): Promise<ModelEvaluationSummary> {
  const res = await client.get<ModelEvaluationSummary>(`/ai/model-evaluations/${id}/summary/`);
  return res.data;
}

/** Delete an evaluation */
export async function deleteModelEvaluation(id: number): Promise<void> {
  await client.delete(`/ai/model-evaluations/${id}/`);
}

// ===== LLM Provider Config (settings endpoint, AI-related) =====

/** LLM provider config persisted at /settings/llm-config/.
 * Mirrors the AiConfigPage ProviderConfig local interface. */
export interface LlmProviderConfig {
  id?: number;
  provider: string;
  api_key: string;
  /** Redacted key preview (e.g. sk-***vpce) returned by the backend; the
   * raw key is write-only and never sent back. */
  api_key_masked?: string;
  api_base: string;
  default_model: string;
  temperature: number;
  max_tokens: number;
  /** Model list under this provider (Phase 1 model management). */
  available_models?: string[];
  is_active: boolean;
  last_tested_at?: string;
  test_status?: 'success' | 'failed' | null;
}

/** Fetch all LLM provider configs.
 * Endpoint GET /settings/llm-config/ returns a paginated envelope
 * ({ count, next, previous, results }) — unwrap to the array so the
 * UI always gets a list (Phase 1: multi-provider management). */
export async function fetchLlmProviderConfig(): Promise<LlmProviderConfig[]> {
  const res = await client.get<PaginatedResponse<LlmProviderConfig>>('/settings/llm-config/');
  if (Array.isArray(res.data)) return res.data;
  return res.data?.results ?? [];
}

/** Create new LLM provider config.
 * NOTE: actual endpoint is POST /settings/llm-config/. */
export async function createLlmProviderConfig(payload: Partial<LlmProviderConfig>): Promise<LlmProviderConfig> {
  const res = await client.post<LlmProviderConfig>('/settings/llm-config/', payload);
  return res.data;
}

/** Update existing LLM provider config.
 * NOTE: actual endpoint is PUT /settings/llm-config/{id}/. */
export async function updateLlmProviderConfig(
  id: number,
  payload: Partial<LlmProviderConfig>,
): Promise<LlmProviderConfig> {
  const res = await client.put<LlmProviderConfig>(`/settings/llm-config/${id}/`, payload);
  return res.data;
}

/** Delete an LLM provider config (Phase 1 multi-provider management). */
export async function deleteLlmProviderConfig(id: number): Promise<void> {
  await client.delete(`/settings/llm-config/${id}/`);
}

/** Set an LLM provider as the single active one (backend demotes others). */
export async function setActiveLlmProvider(id: number): Promise<LlmProviderConfig> {
  const res = await client.post<LlmProviderConfig>(`/settings/llm-config/${id}/set-active/`);
  return res.data;
}

/** Per-provider connection test result (POST /settings/llm-config/{id}/test/). */
export interface LlmTestResult {
  success: boolean;
  latency_ms?: number;
  model?: string;
  message?: string;
}

/** Test connectivity to a specific LLM provider.
 * Endpoint POST /settings/llm-config/{id}/test/ (Phase 1 per-provider test). */
export async function testLlmProvider(id: number): Promise<LlmTestResult> {
  const res = await client.post<LlmTestResult>(`/settings/llm-config/${id}/test/`);
  return res.data;
}

// ===== LLM Connection Test (chat endpoint) =====

/** Chat completion response shape (OpenAI-compatible or simple {content} form). */
export interface ChatCompletionResponse {
  content?: string;
  choices?: Array<{ message?: { content?: string } }>;
}

/** Test LLM connection via /ai/chat/ with a tiny prompt.
 * @param payload - chat request body (model + messages + optional sampling params)
 * @param options - optional axios config (e.g. { timeout: 15000 }) */
export async function testLlmConnection(
  payload: {
    model: string;
    messages: Array<{ role: string; content: string }>;
    max_tokens?: number;
    temperature?: number;
  },
  options?: { timeout?: number },
): Promise<ChatCompletionResponse> {
  const res = await client.post<ChatCompletionResponse>(
    '/ai/chat/',
    payload,
    options ? { timeout: options.timeout } : undefined,
  );
  return res.data;
}

// ===== Custom Skills (YAML editor) =====

/** Custom skill definition (YAML-based, /ai/custom-skills/ endpoint). */
export interface CustomSkill {
  id: string;
  name: string;
  description: string;
  category: string;
  yaml_content: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** Fetch custom skills list.
 * Backend may return either an array or a paginated { results: [...] } object. */
export async function fetchCustomSkills(): Promise<CustomSkill[] | { results: CustomSkill[] }> {
  const res = await client.get<CustomSkill[] | { results: CustomSkill[] }>('/ai/custom-skills/');
  return res.data;
}

/** Create a new custom skill. */
export async function createCustomSkill(skillData: Partial<CustomSkill>): Promise<CustomSkill> {
  const res = await client.post<CustomSkill>('/ai/custom-skills/', skillData);
  return res.data;
}

/** Delete a custom skill by id. */
export async function deleteCustomSkill(id: string): Promise<void> {
  await client.delete(`/ai/custom-skills/${id}/`);
}

// ===== Anomaly Detection =====

/** Anomaly detection request payload. */
export interface AnomalyDetectionPayload {
  days: number;
  min_occurrences: number;
}

/** Anomaly detection result (LLM-analyzed recurring failure patterns).
 * Matches AnomalyPatternPanel local AnomalyResult interface. */
export interface AnomalyDetectionResult {
  patterns: Array<{
    pattern_text: string;
    occurrence_count: number;
    severity: 'critical' | 'high' | 'medium' | 'low';
    category: string;
    sample_messages: string[];
    first_seen: string;
  }>;
  summary: string;
  llm_analysis: string | null;
  stats: {
    failed_count: number;
    total_count: number;
    failure_rate: number;
    unique_errors: number;
  };
  total_analyzed: number;
}

/** Run anomaly detection analysis. */
export async function detectAnomalies(payload: AnomalyDetectionPayload): Promise<AnomalyDetectionResult> {
  const res = await client.post<AnomalyDetectionResult>('/ai/anomaly-detection/', payload);
  return res.data;
}

// ===== AI Usage Stats =====

/** AI usage stats response (all fields optional — backend may omit). */
export interface AiUsageStats {
  total_requests?: number;
  success_rate?: number;
  total_tokens?: number;
  estimated_cost?: number;
  model_distribution?: Array<{ name: string; value: number }>;
  daily_trend?: Array<{ date: string; requests: number; tokens: number }>;
}

/** Fetch AI usage statistics.
 * @param params - e.g. { days: 30 } */
export async function fetchAiUsageStats(params?: { days?: number }): Promise<AiUsageStats> {
  const res = await client.get<AiUsageStats>('/ai/usage-stats/', { params });
  return res.data ?? {};
}

// ===== Pipeline Optimization =====

/** Optimize pipeline request payload. */
export interface OptimizePipelinePayload {
  pipeline_id: string;
  model: string;
}

/** Request AI optimization suggestions for a pipeline. */
export async function optimizePipeline(payload: OptimizePipelinePayload): Promise<Record<string, unknown>> {
  const res = await client.post<Record<string, unknown>>('/ai/optimize-pipeline/', payload);
  return res.data;
}

// ===== Execution Log Analysis =====

/** Execution log analysis result (steps + summary + suggestions).
 * NOTE: actual endpoint is GET /executions/{executionId}/analysis (executions
 * domain, AI-powered analysis). Matches LogAnalysisPanel local interface. */
export interface ExecutionLogAnalysis {
  steps: Array<{ name: string; status: string; duration_ms: number; error?: string }>;
  summary: string;
  suggestions: string[];
}

/** Fetch AI analysis for a specific execution's logs.
 * NOTE: actual endpoint is GET /executions/{executionId}/analysis. */
export async function fetchExecutionAnalysis(executionId: string): Promise<ExecutionLogAnalysis> {
  const res = await client.get<ExecutionLogAnalysis>(`/executions/${executionId}/analysis`);
  return res.data;
}

// ===== Agent Deep Analysis (LangGraph ReAct) =====

/** A single ReAct reasoning step: thought → action → observation. */
export interface AgentReasoningStep {
  thought: string;
  action: string | null;
  action_input: Record<string, unknown> | null;
  observation: string | null;
}

/** Agent deep analysis result.
 *  - POST /ai/agent/analyze/ returns {session_id, status: 'pending'}
 *  - GET  /ai/agent/sessions/<id>/ returns the full result once completed.
 *  The `status` field transitions: pending → running → completed | failed.
 */
export interface AgentAnalysisResult {
  session_id: number;
  status: 'pending' | 'running' | 'completed' | 'failed';
  model_used: string;
  reasoning_steps: AgentReasoningStep[];
  summary: string;
  suggestions: string[];
  total_tokens: number;
  error?: string | null;
  /** Optional dispatch message included in the POST response. */
  message?: string;
}

/** Dispatch deep analysis via the LangGraph ReAct agent (async).
 * Returns immediately with {session_id, status: 'pending'}; the caller
 * should then poll fetchAgentSessionStatus(session_id) every few seconds
 * until status becomes 'completed' or 'failed'.
 * @param executionId - TaskExecution ID to analyze
 */
export async function analyzeExecutionWithAgent(executionId: string | number): Promise<AgentAnalysisResult> {
  const res = await client.post<AgentAnalysisResult>('/ai/agent/analyze/', {
    execution_id: Number(executionId),
  });
  return res.data;
}

/** Poll the status of a dispatched agent analysis session.
 * Call this every 3 seconds after analyzeExecutionWithAgent() returns
 * a session_id. Stop polling when status === 'completed' | 'failed'.
 * @param sessionId - AgentSession ID returned from analyzeExecutionWithAgent
 */
export async function fetchAgentSessionStatus(sessionId: number): Promise<AgentAnalysisResult> {
  const res = await client.get<AgentAnalysisResult>(`/ai/agent/sessions/${sessionId}/`);
  return res.data;
}

// ─────────────────────────────────────────────
// QA multi-turn conversation (from qa.ts, merged 2026-08-04)
// ─────────────────────────────────────────────

/** Budget info shape returned by QASessionViewSet.budget action. */
export interface BudgetInfo {
  budget: number;
  usage: number;
  percentage: number;
  status: 'normal' | 'warning' | 'exceeded';
}

/** QA message shape — matches backend QAMessageSerializer. */
export interface QAMessage {
  id: number;
  session: number;
  role: 'user' | 'assistant' | 'system' | string;
  content: string;
  created_at: string;
}

/** Get current user's LLM budget info (QASessionViewSet.budget action). */
export async function fetchBudgetInfo(): Promise<BudgetInfo> {
  const res = await client.get<BudgetInfo>('/qa/qa-sessions/budget/');
  return res.data;
}

/** List QA sessions (paginated). */
export async function fetchQASessions(params?: {
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<QASession>> {
  const res = await client.get<PaginatedResponse<QASession>>('/qa/qa-sessions/', { params });
  return res.data;
}

/** Ask a question (AskView). Creates a new QASession when session_id is
 * omitted, or appends to an existing conversation when session_id is set. */
export async function askQuestion(data: QAAskRequest): Promise<QAAskResponse> {
  const res = await client.post<QAAskResponse>('/qa/ask/', data);
  return res.data;
}

/** Toggle knowledge entry flag on a QA session. */
export async function markAsKnowledge(sessionId: number): Promise<QASession> {
  const res = await client.post<QASession>(`/qa/qa-sessions/${sessionId}/mark-knowledge/`);
  return res.data;
}

/** Fetch messages for a QA session. */
export async function fetchQASessionMessages(sessionId: number): Promise<QAMessage[]> {
  const res = await client.get<QAMessage[]>('/qa/messages/by_session/', {
    params: { session: sessionId },
  });
  return res.data;
}

/** Create a new QA session. */
export async function createQASession(payload: {
  question: string;
  title?: string;
  context_snapshot?: Record<string, unknown>;
}): Promise<QASession> {
  const res = await client.post<QASession>('/qa/qa-sessions/', payload);
  return res.data;
}

/** Send a message to a QA session. */
export async function sendQAMessage(sessionId: number, payload: { role: string; content: string }): Promise<QAMessage> {
  const res = await client.post<QAMessage>('/qa/messages/', {
    session: sessionId,
    role: payload.role,
    content: payload.content,
  });
  return res.data;
}

/** Delete a QA session (cascades to all its QAMessage rows). */
export async function deleteQASession(sessionId: number): Promise<void> {
  await client.delete(`/qa/qa-sessions/${sessionId}/`);
}
