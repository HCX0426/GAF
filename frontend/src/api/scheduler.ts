/**
 * scheduler center related API
 *
 * includes time window CRUD, warmup config Upsert, execution plan preview,
 * today schedule, auto stop condition Upsert etc. API.
 */

import client from './client';
import type {
  AutoStopCondition,
  ExecutionPlanResponse,
  PaginatedResponse,
  ScheduledTask,
  CreateScheduledTaskRequest,
  TimeWindow,
  TodayScheduleResponse,
  WarmupConfig,
} from '@/types/models';

/** get time window list */
export async function fetchTimeWindows(params?: { enabled?: boolean }): Promise<TimeWindow[]> {
  const res = await client.get<TimeWindow[]>('/scheduler/time-windows/', { params });
  return res.data;
}

/** get single time window */
export async function fetchTimeWindow(id: number): Promise<TimeWindow> {
  const res = await client.get<TimeWindow>(`/scheduler/time-windows/${id}/`);
  return res.data;
}

/** create time window */
export async function createTimeWindow(data: Partial<TimeWindow>): Promise<TimeWindow> {
  const res = await client.post<TimeWindow>('/scheduler/time-windows/', data);
  return res.data;
}

/** update time window */
export async function updateTimeWindow(id: number, data: Partial<TimeWindow>): Promise<TimeWindow> {
  const res = await client.put<TimeWindow>(`/scheduler/time-windows/${id}/`, data);
  return res.data;
}

/** delete time window */
export async function deleteTimeWindow(id: number): Promise<void> {
  await client.delete(`/scheduler/time-windows/${id}/`);
}

/** get warmup config */
export async function fetchWarmupConfig(): Promise<WarmupConfig> {
  const res = await client.get<WarmupConfig>('/scheduler/warmup-config/');
  return res.data;
}

/** create/update warmup config (Upsert) */
export async function upsertWarmupConfig(data: WarmupConfig): Promise<WarmupConfig> {
  const res = await client.post<WarmupConfig>('/scheduler/warmup-config/', data);
  return res.data;
}

/** get auto-stop conditions list */
export async function fetchAutoStopConditions(): Promise<{ conditions: AutoStopCondition[] }> {
  const res = await client.get<{ conditions: AutoStopCondition[] }>('/scheduler/auto-stop-conditions/');
  return res.data;
}

/** update auto-stop conditions (Upsert) */
export async function upsertAutoStopConditions(data: {
  conditions: Partial<AutoStopCondition>[];
}): Promise<{ conditions: AutoStopCondition[] }> {
  const res = await client.post<{ conditions: AutoStopCondition[] }>('/scheduler/auto-stop-conditions/', data);
  return res.data;
}

/** get execution plan preview */
export async function fetchExecutionPlan(days?: number): Promise<ExecutionPlanResponse> {
  const res = await client.get<ExecutionPlanResponse>('/scheduler/execution-plan/', {
    params: { days: days ?? 7 },
  });
  return res.data;
}

/** get today schedule */
export async function fetchTodaySchedule(options?: { signal?: AbortSignal }): Promise<TodayScheduleResponse> {
  const res = await client.get<TodayScheduleResponse>('/scheduler/today/', { signal: options?.signal });
  return res.data;
}

// ─────────────────────────────────────────────
// P-020-C: recovery operation log API
// ─────────────────────────────────────────────

/** single recovery log record */
export interface RecoveryLogEntry {
  id: number;
  recovery_level: 'step' | 'task' | 'app' | 'device' | 'system';
  recovery_level_display: string;
  trigger_event: string;
  action_taken: string;
  success: boolean;
  details: Record<string, unknown>;
  created_at: string;
}

/** get recovery log list (P-020-C) */
export async function fetchRecoveryLogs(params?: {
  recovery_level?: 'step' | 'task' | 'app' | 'device' | 'system';
  success?: boolean;
}): Promise<RecoveryLogEntry[]> {
  const res = await client.get<RecoveryLogEntry[]>('/scheduler/recovery-logs/', { params });
  return res.data;
}

/** get single recovery log details (P-020-C) */
export async function fetchRecoveryLog(id: number): Promise<RecoveryLogEntry> {
  const res = await client.get<RecoveryLogEntry>(`/scheduler/recovery-logs/${id}/`);
  return res.data;
}

// ─────────────────────────────────────────────
// Scheduled execution history (Ops > ScheduledTasks > history tab)
// ─────────────────────────────────────────────

/** Scheduled execution history record */
export interface ScheduledExecutionRecord {
  id: string;
  task_name: string;
  scheduled_task_id: string;
  status: 'success' | 'failed' | 'timeout' | 'running';
  started_at: string;
  finished_at?: string;
  duration_seconds?: number;
  error_message?: string;
}

/** Fetch scheduled execution history list (paginated) */
export async function fetchSchedulerExecutions(params?: {
  page?: number;
  page_size?: number;
  signal?: AbortSignal;
}): Promise<PaginatedResponse<ScheduledExecutionRecord>> {
  const { signal, ...queryParams } = params || {};
  const res = await client.get<PaginatedResponse<ScheduledExecutionRecord>>('/scheduler/executions/', {
    params: queryParams,
    signal,
  });
  return res.data;
}

// ─────────────────────────────────────────────
// Scheduled Task CRUD (from scheduledTasks.ts, merged 2026-08-04)
// ─────────────────────────────────────────────

/** Fetch scheduled task list */
export async function fetchScheduledTasks(params?: {
  page?: number;
  page_size?: number;
  signal?: AbortSignal;
}): Promise<PaginatedResponse<ScheduledTask>> {
  const { signal, ...queryParams } = params || {};
  const res = await client.get<PaginatedResponse<ScheduledTask>>('/tasks/scheduled-tasks/', {
    params: queryParams,
    signal,
  });
  return res.data;
}

/** Create scheduled task */
export async function createScheduledTask(data: CreateScheduledTaskRequest): Promise<ScheduledTask> {
  const res = await client.post<ScheduledTask>('/tasks/scheduled-tasks/', data);
  return res.data;
}

/** Update scheduled task */
export async function updateScheduledTask(
  id: number,
  data: Partial<CreateScheduledTaskRequest>,
): Promise<ScheduledTask> {
  const res = await client.put<ScheduledTask>(`/tasks/scheduled-tasks/${id}/`, data);
  return res.data;
}

/** Delete scheduled task */
export async function deleteScheduledTask(id: number): Promise<void> {
  await client.delete(`/tasks/scheduled-tasks/${id}/`);
}

/** Toggle scheduled task enabled status */
export async function toggleScheduledTask(id: number): Promise<void> {
  await client.post(`/tasks/scheduled-tasks/${id}/toggle/`);
}
