/**
 * Log Entry API — unified application log persistence layer.
 * Read-only: list and retrieve LogEntry records created by DatabaseLogHandler.
 *
 * Also provides the unified UNION timeline API (C.5) that stitches together
 * 6 specialized log models into a single chronological view.
 */
import client from './client';
import type { LogEntry, PaginatedResponse } from '@/types/models';

/** Fetch log entries (paginated, filterable by level/source/time-range/entity-ids/trace_id). */
export async function fetchLogEntries(params?: {
  page?: number;
  page_size?: number;
  level?: string;
  source?: string;
  start?: string;
  end?: string;
  task_id?: number;
  agent_id?: number;
  device_id?: number;
  trace_id?: string;
  search?: string;
  ordering?: string;
}): Promise<PaginatedResponse<LogEntry>> {
  const res = await client.get<PaginatedResponse<LogEntry>>('/logs/', { params });
  return res.data;
}

/** Fetch a single log entry by ID. */
export async function fetchLogEntry(id: number | string): Promise<LogEntry> {
  const res = await client.get<LogEntry>(`/logs/${id}/`);
  return res.data;
}

/** Normalized row returned by the UNION timeline endpoint. */
export interface UnifiedLogEntry {
  /** Source model class name (LogEntry / AuditLog / RecoveryLog / ...) */
  ref_type: string;
  /** PK in the source table */
  ref_id: number;
  /** ISO timestamp */
  occurred_at: string;
  /** Normalized level: DEBUG / INFO / WARNING / ERROR / CRITICAL */
  log_level: string;
  /** Source label, e.g. "audit.login" / "recovery.step" / "crash.ScreenshotService" */
  log_source: string;
  /** Human-readable summary */
  log_message: string;
}

/** Response shape from /api/v2/logs/timeline/ */
export interface UnifiedTimelineResponse {
  count: number;
  page: number;
  page_size: number;
  results: UnifiedLogEntry[];
}

/** Fetch the unified UNION timeline across 6 specialized log models. */
export async function fetchUnifiedTimeline(params?: {
  page?: number;
  page_size?: number;
  level?: string;
  source?: string;
  start?: string;
  end?: string;
}): Promise<UnifiedTimelineResponse> {
  const res = await client.get<UnifiedTimelineResponse>('/logs/timeline/', { params });
  return res.data;
}

/** File log line queried from /logs/files/ (spec 2026-08-29-logging-system-consolidation P2-1). */
export interface FileLogLine {
  service: string;
  date: string | null;
  path: string | null;
  files: string[];
  filter: 'all' | 'error';
  lines: string[];
  error_count: number | null;
}

/** GET /logs/files/ — 统一文件日志检索 (服务终端 + 原生日志 tail / 报错过滤). */
export async function fetchFileLogs(params: {
  service: string;
  lines?: number;
  filter?: 'all' | 'error';
  date?: string;
}): Promise<FileLogLine> {
  const res = await client.get<FileLogLine>('/logs/files/', { params });
  return res.data;
}

// ─────────────────────────────────────────────
// C.5: Specialty log list APIs (minimal read-only access for LogCenterPage tabs)
// ─────────────────────────────────────────────

/** MessageFrameLog row (protocol app). */
export interface MessageFrameLogEntry {
  id: number;
  trace_id: string;
  message_type: string;
  direction: 'inbound' | 'outbound';
  payload: Record<string, unknown>;
  agent_session: number | null;
  created_at: string;
}

/** Fetch message frame logs (paginated). */
export async function fetchMessageFrameLogs(params?: {
  page?: number;
  page_size?: number;
  message_type?: string;
  direction?: string;
}): Promise<PaginatedResponse<MessageFrameLogEntry>> {
  const res = await client.get<PaginatedResponse<MessageFrameLogEntry>>('/protocol/messages/', { params });
  return res.data;
}

/** LLMUsageLog row (qa app). */
export interface LLMUsageLogEntry {
  id: number;
  user: number | null;
  model_name: string;
  input_tokens: number;
  output_tokens: number;
  cost_estimate: string;
  call_type: string;
  route: string;
  created_at: string;
}

/** Fetch LLM usage logs (paginated). */
export async function fetchLLMUsageLogs(params?: {
  page?: number;
  page_size?: number;
  model_name?: string;
  call_type?: string;
}): Promise<PaginatedResponse<LLMUsageLogEntry>> {
  const res = await client.get<PaginatedResponse<LLMUsageLogEntry>>('/qa/llm-usage-logs/', { params });
  return res.data;
}

/** CrashReport row (debug app). */
export interface CrashReportEntry {
  id: number;
  component: string;
  error_type: string;
  stack_trace: string;
  system_info: Record<string, unknown>;
  resolved: boolean;
  created_at: string;
}

/** Fetch crash reports (paginated). */
export async function fetchCrashReports(params?: {
  page?: number;
  page_size?: number;
  component?: string;
  resolved?: boolean;
}): Promise<PaginatedResponse<CrashReportEntry>> {
  const res = await client.get<PaginatedResponse<CrashReportEntry>>('/debug/crash-reports/', { params });
  return res.data;
}
