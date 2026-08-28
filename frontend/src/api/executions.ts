/**
 * Execution management API
 * Covers execution detail, steps, intervene, pause/resume/skip/cancel/fail
 */
import client from './client';
import type { TaskExecution, TaskStep, PaginatedResponse, StepStatus } from '@/types/models';

/** Execution steps response */
export interface ExecutionStepsResponse {
  execution_id: number;
  total_steps: number;
  completed_steps: number;
  steps: TaskStep[];
}

/** Intervene response */
export interface InterveneResponse {
  success: boolean;
  message: string;
  new_status: string;
}

/** Fetch all executions */
export async function fetchAllExecutions(params?: Record<string, unknown>): Promise<PaginatedResponse<TaskExecution>> {
  const res = await client.get<PaginatedResponse<TaskExecution>>('/tasks/task-executions/', { params });
  return res.data;
}

/** Fetch single execution */
export async function fetchExecution(executionId: number): Promise<TaskExecution> {
  const res = await client.get<TaskExecution>(`/tasks/task-executions/${executionId}/`);
  return res.data;
}

/** Fetch execution steps */
export async function fetchExecutionSteps(executionId: number, stepIndex?: number): Promise<ExecutionStepsResponse> {
  const params = stepIndex !== undefined ? { step_index: stepIndex } : {};
  const res = await client.get<ExecutionStepsResponse>(`/executions/${executionId}/steps/`, { params });
  return res.data;
}

/** Intervene in execution (pause/resume/skip_step/fail_step/cancel).
 *  Action names MUST match backend valid_actions in backend/executions/views.py.
 *  Legacy 'skip'/'fail' aliases were removed in L3-1 Round 9 (spec 2026-07-17-l3-round9). */
export async function interveneExecution(
  executionId: number,
  action: 'pause' | 'resume' | 'skip_step' | 'fail_step' | 'cancel',
  reason?: string,
): Promise<InterveneResponse> {
  const res = await client.post<InterveneResponse>(`/executions/${executionId}/intervene/`, { action, reason });
  return res.data;
}

/** Pause execution */
export async function pauseExecution(executionId: number, reason?: string): Promise<InterveneResponse> {
  return interveneExecution(executionId, 'pause', reason);
}

/** Resume execution */
export async function resumeExecution(executionId: number, reason?: string): Promise<InterveneResponse> {
  return interveneExecution(executionId, 'resume', reason);
}

/** Skip current step (uses 'skip_step' to match backend valid_actions) */
export async function skipExecutionStep(executionId: number, reason?: string): Promise<InterveneResponse> {
  return interveneExecution(executionId, 'skip_step', reason);
}

/** Cancel execution */
export async function cancelExecution(executionId: number, reason?: string): Promise<InterveneResponse> {
  return interveneExecution(executionId, 'cancel', reason);
}

/** Fail a specific step */
export async function failExecutionStep(executionId: number, reason?: string): Promise<InterveneResponse> {
  return interveneExecution(executionId, 'fail_step', reason);
}

/** Force fail an entire execution (uses 'fail_step' on the current step;
 *  backend has no 'fail' whole-execution action, so we reuse fail_step) */
export async function forceFailExecution(executionId: number, reason?: string): Promise<InterveneResponse> {
  return interveneExecution(executionId, 'fail_step', reason);
}

/**
 * Daily execution report (F005 fix: migrated from raw fetch() in DailyReportViewer).
 * Returns summary + itemized executions for the given date.
 */
export async function getDailyReport(date: string): Promise<DailyReportData> {
  const res = await client.get<DailyReportData>('/executions/daily-report/', { params: { date } });
  return res.data;
}

/**
 * Unattended execution logs (F005 fix: migrated from raw fetch() in UnattendedLogViewer).
 * Returns flat log entries grouped by device/account on the client side.
 */
export async function getUnattendedLogs(date: string): Promise<UnattendedLogEntry[]> {
  const res = await client.get<UnattendedLogEntry[]>('/executions/unattended-logs/', { params: { date } });
  return res.data;
}

/** Daily report summary section */
export interface DailyReportSummary {
  date: string;
  total_executions: number;
  success_count: number;
  failed_count: number;
  avg_duration: string;
}

/** Daily report item row */
export interface DailyReportItem {
  id: string;
  task_name: string;
  device_name: string;
  account_name: string;
  status: 'success' | 'failed' | 'running' | 'pending';
  started_at: string;
  completed_at: string | null;
  duration: string;
  error_message?: string;
}

/** Full daily report response */
export interface DailyReportData {
  summary: DailyReportSummary;
  items: DailyReportItem[];
  results?: DailyReportItem[]; // alias some backends use
  generated_at: string;
}

/** Unattended log entry (flat, grouped client-side) */
export interface UnattendedLogEntry {
  id: string;
  timestamp: string;
  event_type: 'start' | 'stop' | 'error' | 'recover' | 'switch' | 'complete';
  level: 'INFO' | 'WARN' | 'ERROR' | 'SUCCESS';
  message: string;
  device_name: string;
  account_name: string;
}

// ─────────────────────────────────────────────
// Execution replay (Ops > ExecutionReplay)
// ─────────────────────────────────────────────

/** Single frame in an execution replay timeline */
export interface ExecutionReplayFrame {
  index: number;
  imageBase64: string;
  timestamp: string;
  stepIndex: number;
}

/** Step metadata shown alongside replay frames */
export interface ExecutionReplayStep {
  index: number;
  name: string;
  status: StepStatus;
  duration?: number;
  frameStart: number;
  frameEnd: number;
}

/** Replay payload returned by /task-executions/{id}/replay/ */
export interface ExecutionReplayData {
  frames?: ExecutionReplayFrame[];
  steps?: ExecutionReplayStep[];
}

/**
 * Fetch execution replay data (frames + step metadata) for the Ops replay viewer.
 * GET /tasks/task-executions/{executionId}/replay/
 */
export async function fetchExecutionReplay(executionId: string | number): Promise<ExecutionReplayData> {
  const res = await client.get<ExecutionReplayData>(`/tasks/task-executions/${executionId}/replay/`);
  return res.data;
}

// ─────────────────────────────────────────────
// Retry from step (Task 1.1 — B7 重试单节点)
// ─────────────────────────────────────────────

/** Task 1.1: retry-from-step response payload. */
export interface RetryFromStepResponse {
  new_execution_id: number;
  status: string;
  retry_from_step_index: number;
  previous_results_count: number;
}

/**
 * Task 1.1 (B7 重试单节点, P0-1): Retry execution from a failed step.
 *
 * Creates a new TaskExecution that re-runs only the failed node + downstream
 * nodes, reusing the previously-succeeded step results. The original failed
 * execution is preserved unchanged for audit/diagnosis.
 *
 * Endpoint: POST /tasks/task-executions/{executionId}/retry-from-step/
 * Body: { step_index: number } — must reference an existing FAILED step.
 *
 * Returns the new execution's id + status so the frontend can navigate
 * to the new execution's monitor panel.
 */
export async function retryFromStep(executionId: number, stepIndex: number): Promise<RetryFromStepResponse> {
  const res = await client.post(`/tasks/task-executions/${executionId}/retry-from-step/`, {
    step_index: stepIndex,
  });
  // Backend wraps the response via UnifiedResponseMiddleware as
  // { code, message, data }. The axios client interceptor already unwraps
  // to ``data`` for success responses, so res.data is the payload directly.
  // Be defensive: support both unified (res.data.data) and raw shapes.
  const payload = res.data;
  if (payload && typeof payload === 'object' && 'data' in payload && payload.data) {
    return payload.data as RetryFromStepResponse;
  }
  return payload as RetryFromStepResponse;
}
