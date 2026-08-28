/**
 * debug domain models (s37 split from models.ts — TD-365).
 */

export type AnalysisStatus = 'pending' | 'analyzing' | 'completed' | 'failed';

/** debug log archive — field names mirror backend DebugLogArchiveSerializer
 * (id/zip_file_path/uploaded_at/analysis_status/skill/uploaded_by).
 */

export interface DebugLogArchive {
  id: string;
  zip_file_path: string;
  uploaded_at: string;
  analysis_status: AnalysisStatus;
  skill: string | null;
  uploaded_by: string | null;
}

/** LLM analysis review status — matches backend LLMAnalysisResult.ReviewStatus choices */

export type ReviewStatus = 'pending' | 'adopted' | 'ignored' | 'investigating';

/** LLM analysis result — field names mirror backend LLMAnalysisResultSerializer
 * (id/log_archive/skill/result_data/suggestions/review_status/confidence/model_name/created_at).
 * NOTE: there is no per-result `status` field; the archive-level
 * `analysis_status` (pending/analyzing/completed) lives on DebugLogArchive.
 * `result_data` and `suggestions` are JSONField on the backend.
 */

export interface LLMAnalysisResult {
  id: string;
  log_archive: string;
  skill: string | null;
  review_status: ReviewStatus;
  result_data: Record<string, unknown> | null;
  suggestions: string[] | null;
  confidence: number | null;
  model_name: string;
  created_at: string;
}

/** Alias kept for legacy callers that treated each archive row as a "DebugLog". */

export type DebugLog = DebugLogArchive;

/** Alias kept for legacy callers that referred to analysis results as "DebugSuggestion". */

export type DebugSuggestion = LLMAnalysisResult;

/** QA session — matches backend QASessionSerializer (S4 multi-turn QA).
 * QASession is the conversation aggregate root; individual messages live
 * in QAMessage (see frontend/src/api/qa.ts). */

export interface QASession {
  id: number;
  title: string;
  question: string;
  context_snapshot: Record<string, unknown>;
  answer: string;
  is_knowledge_entry: boolean;
  user: number | null;
  model_name: string;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

/** QA question request — matches backend AskSerializer.
 * context is a JSON object (JSONField on backend); session_id continues
 * an existing conversation (S4 multi-turn QA). */

export interface QAAskRequest {
  question: string;
  context?: Record<string, unknown>;
  session_id?: number;
}

/** QA ask response — the backend AskView returns a full QASession object. */

export type QAAskResponse = QASession;

/**
 * @deprecated 旧 chain schema 的 UI-internal flat representation。
 * 字段名仍用旧 chain schema (action_type / retry_count / retry_interval / fallback_action / next_step),
 * 保存时由 stepToPipelineNode() 转换为 PipelineNode schema (canonical)。
 * 新代码应直接使用 PipelineNode schema,不要使用此 interface。
 * Task 4.57 (P1-37, 2026-07-28): 标注 @deprecated 提示新人。
 *
 * Task step config — UI-internal flat representation used by TaskEditorPage.
 *
 * spec-2026-07-27-execution-path-unification: chain schema 已废弃, agent parser
 * 只识别 PipelineNode schema (node_type/config/retry/fallback/next_node_id).
 * 此接口仅作为表单内部状态, 保存时由 Editor.tsx 的 stepToPipelineNode() 转换为
 * PipelineNode schema 写入 task_definition.nodes. 不要在新的消费者里直接读取
 * 这些 flat 字段 — 应改为读取 task_definition.nodes[i].node_type 等规范字段。
 *
 * 字段映射 (TaskStepConfigLegacy → PipelineNode):
 *   action_type                  → node_type
 *   retry_count + retry_interval → retry: {max_retries, base_delay}
 *   fallback_action              → fallback: {action}
 *   next_step                    → next_node_id
 *   template_id/roi/condition    → config: {...}
 */
