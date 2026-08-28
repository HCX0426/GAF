/**
 * Miscellaneous API functions for endpoints not yet covered by domain modules.
 *
 * Each function here corresponds to an endpoint that does not logically fit
 * into any existing domain module (devices, agents, init, scheduledTasks,
 * alertRules, accounts, auth, scheduler, settings, tasks, monitors,
 * resources, etc.). When a future refactor introduces a dedicated module
 * for one of these endpoints, the function should move there.
 */
import client from './client';
import type { User, Plugin, ProgressData } from '@/types/models';

// ===================== User =====================

/** GET /accounts/users/me/ — fetch the currently authenticated user. */
export async function fetchCurrentUser(): Promise<User> {
  const res = await client.get<User>('/accounts/users/me/');
  return res.data;
}

// ===================== Notifications =====================

/** GET /notifications/unread-count/ — fetch unread notification count. */
export async function fetchUnreadCount(signal?: AbortSignal): Promise<{ unread_count: number }> {
  const res = await client.get<{ unread_count: number }>('/notifications/unread-count/', { signal });
  return res.data;
}

/** GET /notifications/preferences/ — fetch notification preferences. */
export async function fetchNotificationPreferences<T = Record<string, unknown>>(): Promise<T> {
  const res = await client.get<T>('/notifications/preferences/');
  return res.data;
}

/** POST /notifications/preferences/ — save notification preferences. */
export async function saveNotificationPreferences<T = Record<string, unknown>>(payload: T): Promise<T> {
  const res = await client.post<T>('/notifications/preferences/', payload);
  return res.data;
}

/** GET /notifications/webhooks/ — fetch webhook list. */
export async function fetchWebhooks<T = unknown>(): Promise<T> {
  const res = await client.get<T>('/notifications/webhooks/');
  return res.data;
}

/** POST /notifications/webhooks/ — create a webhook config. */
export async function createWebhook<T = unknown>(payload: T): Promise<T> {
  const res = await client.post<T>('/notifications/webhooks/', payload);
  return res.data;
}

/** PATCH /notifications/webhooks/:id/ — partially update a webhook config. */
export async function updateWebhook<T = unknown>(id: number, payload: Partial<T>): Promise<T> {
  const res = await client.patch<T>(`/notifications/webhooks/${id}/`, payload);
  return res.data;
}

/** DELETE /notifications/webhooks/:id/ — delete a webhook config. */
export async function deleteWebhook(id: number): Promise<void> {
  await client.delete(`/notifications/webhooks/${id}/`);
}

/** POST /notifications/webhooks/:id/test/ — send a test payload to a webhook. */
export async function testWebhook<T = unknown>(id: number): Promise<T> {
  const res = await client.post<T>(`/notifications/webhooks/${id}/test/`);
  return res.data;
}

// ===================== Monitors =====================

/** GET /monitors/status/ — fetch overall system status for the header indicator. */
export async function fetchSystemStatus<T = unknown>(signal?: AbortSignal): Promise<T> {
  const res = await client.get<T>('/monitors/status/', { signal });
  return res.data;
}

// ===================== Resources =====================

/** GET /resources/templates/ — fetch pipeline templates list. */
export async function fetchPipelineTemplates<T = unknown[]>(): Promise<T> {
  const res = await client.get<T>('/resources/templates/');
  return res.data;
}

// ===================== Settings (unattended strategy) =====================

/** GET /settings/unattended-strategy/ — fetch unattended strategy config. */
export async function fetchUnattendedStrategy<T = unknown>(): Promise<T> {
  const res = await client.get<T>('/settings/unattended-strategy/');
  return res.data;
}

/** POST /settings/unattended-strategy/ — save unattended strategy config. */
export async function saveUnattendedStrategy<T = unknown>(payload: T): Promise<T> {
  const res = await client.post<T>('/settings/unattended-strategy/', payload);
  return res.data;
}

// ===================== Tasks (versions, chain-nodes) =====================

/** GET /tasks/versions/ — fetch version list for a task. */
export async function fetchTaskVersions<T = unknown>(taskId: number): Promise<T> {
  const res = await client.get<T>('/tasks/versions/', { params: { task_id: taskId } });
  return res.data;
}

/** POST /tasks/:taskId/save-version/ — save a new version snapshot for a task. */
export async function saveTaskVersion<T = unknown>(taskId: number, changeDescription = ''): Promise<T> {
  const res = await client.post<T>(`/tasks/${taskId}/save-version/`, {
    change_description: changeDescription,
  });
  return res.data;
}

// R37-P3 Stage 7 Task 20a: backend TaskChainNode moved from tasks to pipeline
// app (TD-039). Endpoint base changed from /tasks/chain-nodes/ to
// /pipeline/chain-nodes/. db_table unchanged — zero data migration.

/** GET /pipeline/chain-nodes/ — fetch task chain dependency edges for a task. */
export async function fetchTaskChainNodes<T = unknown>(taskId: number): Promise<T> {
  const res = await client.get<T>('/pipeline/chain-nodes/', { params: { task_id: taskId } });
  return res.data;
}

/** POST /pipeline/chain-nodes/ — create a task chain dependency edge. */
export async function createTaskChainNode<T = unknown>(payload: T): Promise<T> {
  const res = await client.post<T>('/pipeline/chain-nodes/', payload);
  return res.data;
}

/** DELETE /pipeline/chain-nodes/:id/ — delete a task chain dependency edge. */
export async function deleteTaskChainNode(id: number): Promise<void> {
  await client.delete(`/pipeline/chain-nodes/${id}/`);
}

/** POST /pipeline/chain-nodes/check-circular/ — check a task chain for circular dependencies. */
export async function checkTaskChainCircular<T = unknown>(taskId: number): Promise<T> {
  const res = await client.post<T>('/pipeline/chain-nodes/check-circular/', {
    task_id: taskId,
  });
  return res.data;
}

// ===================== Scheduler (unattended runtime) =====================

/** Response payload for startUnattended — backend returns at least started_at.
 *
 * P-011: now returns session_id + game_profile_id + game_profile_name so the
 * store can append the new session to its `sessions` array.
 */
export interface StartUnattendedResponse {
  status: string;
  session_id: number;
  game_profile_id: number;
  game_profile_name: string;
  started_at: string;
  rotation_rule_id?: number | null;
  dispatched_count: number;
  skipped_count: number;
  failed_count: number;
  dispatched_chain_execution_ids: number[];
  skipped: Array<{ device_id: number; reason: string }>;
  failed: Array<{ device_id: number; reason: string }>;
  message: string;
}

/** Preflight response — backend returns a checks array. */
export interface UnattendedPreflightResponse {
  checks?: unknown[];
  [key: string]: unknown;
}

/** One active session entry in /scheduler/unattended/status response (P-011). */
export interface ActiveSessionEntry {
  id: number;
  status: string;
  mode_status: 'running' | 'paused' | 'stopped';
  game_profile_id: number | null;
  game_profile_name: string | null;
  started_at: string | null;
  total_devices: number;
  total_accounts: number;
}

/** Backend unattended matrix row (snake_case) — the exact shape
 * `matrixRowToState` in useUnattendedStore consumes. Declared here so the
 * response type is concrete instead of `unknown[]` (TS2345 fix).
 */
export interface UnattendedMatrixRow {
  device_id?: number | string;
  device_name?: string;
  device_status?: string;
  cells?: Array<{
    account_id?: number;
    account_name?: string;
    task_name?: string | null;
    status?: string;
    progress?: number;
    started_at?: string | null;
    error_message?: string | null;
  }>;
}

/** Backend unattended queue entry (snake_case) — consumed by `queueItemToState`. */
export interface UnattendedQueueEntry {
  id?: number;
  device_name?: string;
  account_name?: string;
  task_name?: string;
  estimated_start?: string | null;
  status?: string;
  priority?: number;
}

/** Status matrix response — backend returns a matrix array.
 *
 * P-011: also returns `active_sessions` (list) and aggregated `mode_status`.
 * The frontend store rebuilds its `sessions` array from `active_sessions`.
 */
export interface UnattendedStatusResponse {
  mode_status: 'running' | 'paused' | 'stopped';
  active_sessions: ActiveSessionEntry[];
  total_devices: number;
  total_accounts: number;
  matrix?: UnattendedMatrixRow[];
  [key: string]: unknown;
}

/** Queue response — backend returns a queue array. */
export interface UnattendedQueueResponse {
  queue?: UnattendedQueueEntry[];
  [key: string]: unknown;
}

/** Raw progress response from /scheduler/unattended/progress (snake_case fields). */
export interface UnattendedProgressResponse {
  date: string;
  total_accounts: number;
  completed: number;
  success: number;
  failed: number;
  skipped: number;
  success_rate: number;
  estimated_remaining_seconds: number;
}

/** POST /scheduler/unattended/start — start unattended mode for a game_profile (P-011). */
export async function startUnattended(
  gameProfileId: number,
  reason = '',
  rotationRuleId?: number,
  loopRotation?: boolean,
): Promise<StartUnattendedResponse> {
  const payload: Record<string, unknown> = { game_profile_id: gameProfileId, reason };
  if (rotationRuleId !== undefined) {
    payload.rotation_rule_id = rotationRuleId;
  }
  if (loopRotation !== undefined) {
    payload.loop_rotation = loopRotation;
  }
  const res = await client.post<StartUnattendedResponse>('/scheduler/unattended/start/', payload);
  return res.data;
}

/** POST /scheduler/unattended/stop — stop unattended mode by session_id (P-011). */
export async function stopUnattended(sessionId: number, reason = 'manual'): Promise<void> {
  await client.post('/scheduler/unattended/stop/', { session_id: sessionId, reason });
}

/** POST /scheduler/unattended/pause — pause unattended mode by session_id (P-011). */
export async function pauseUnattended(sessionId: number): Promise<void> {
  await client.post('/scheduler/unattended/pause/', { session_id: sessionId });
}

/** POST /scheduler/unattended/resume — resume unattended mode by session_id (P-011). */
export async function resumeUnattended(sessionId: number): Promise<void> {
  await client.post('/scheduler/unattended/resume/', { session_id: sessionId });
}

/** GET /scheduler/unattended/preflight — fetch preflight checks. */
export async function fetchUnattendedPreflight(gameProfileId?: number): Promise<UnattendedPreflightResponse> {
  const res = await client.get<UnattendedPreflightResponse>('/scheduler/unattended/preflight', {
    params: gameProfileId != null ? { game_profile_id: gameProfileId } : undefined,
  });
  return res.data;
}

/** GET /scheduler/unattended/status — fetch device × account status matrix + active sessions. */
export async function fetchUnattendedStatus(): Promise<UnattendedStatusResponse> {
  const res = await client.get<UnattendedStatusResponse>('/scheduler/unattended/status');
  return res.data;
}

/** GET /scheduler/unattended/queue — fetch execution queue. */
export async function fetchUnattendedQueue(limit = 12): Promise<UnattendedQueueResponse> {
  const res = await client.get<UnattendedQueueResponse>('/scheduler/unattended/queue', { params: { limit } });
  return res.data;
}

/** GET /scheduler/unattended/progress — fetch today's progress data. */
export async function fetchUnattendedProgress(): Promise<ProgressData> {
  const res = await client.get<UnattendedProgressResponse>('/scheduler/unattended/progress');
  const data = res.data;
  return {
    date: data.date,
    totalAccounts: data.total_accounts,
    completed: data.completed,
    success: data.success,
    failed: data.failed,
    skipped: data.skipped,
    successRate: data.success_rate,
    estimatedRemainingSeconds: data.estimated_remaining_seconds,
  };
}

// ===================== App Settings (key/value store) =====================

/** GET /settings/app-settings/ — fetch key/value app settings list. */
export async function fetchAppSettings<T = Array<Record<string, unknown>>>(): Promise<T> {
  const res = await client.get<T>('/settings/app-settings/');
  return res.data;
}

// ===================== Plugins =====================

/** GET /plugins/ — fetch plugin list (array or { results: Plugin[] }). */
export async function fetchPlugins(): Promise<Plugin[]> {
  const res = await client.get<Plugin[] | { results: Plugin[] }>('/plugins/');
  const data = res.data;
  return Array.isArray(data) ? data : (data?.results ?? []);
}

/** POST /plugins/:id/toggle/ — toggle a plugin's enabled state. */
export async function togglePlugin(id: string): Promise<void> {
  await client.post(`/plugins/${id}/toggle/`);
}

/** POST /plugins/:id/uninstall/ — uninstall a plugin. */
export async function uninstallPlugin(id: string): Promise<void> {
  await client.post(`/plugins/${id}/uninstall/`);
}
