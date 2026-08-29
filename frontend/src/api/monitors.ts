/**
 * Monitor rules & events API
 * Covers CRUD for monitor rules, event listing, acknowledge action, diagnose, and auto-fix
 */
import client from './client';
import type { AlertRule, MonitorRule, MonitorEvent, PaginatedResponse } from '@/types/models';

/** Fetch monitor rule list */
export async function fetchMonitorRules(params?: Record<string, unknown>): Promise<PaginatedResponse<MonitorRule>> {
  const res = await client.get<PaginatedResponse<MonitorRule>>('/monitors/monitor-rules/', { params });
  return res.data;
}

/** Create monitor rule */
export async function createMonitorRule(data: Partial<MonitorRule>): Promise<MonitorRule> {
  const res = await client.post<MonitorRule>('/monitors/monitor-rules/', data);
  return res.data;
}

/** Update monitor rule */
export async function updateMonitorRule(ruleId: number, data: Partial<MonitorRule>): Promise<MonitorRule> {
  const res = await client.put<MonitorRule>(`/monitors/monitor-rules/${ruleId}/`, data);
  return res.data;
}

/** Delete monitor rule */
export async function deleteMonitorRule(ruleId: number): Promise<void> {
  await client.delete(`/monitors/monitor-rules/${ruleId}/`);
}

/**
 * Notification chain health (TD-421).
 * GET /api/v2/monitors/chain-health/
 * 让通知中心区分"没有告警" vs "告警链路断了"。
 */
export interface NotificationChainHealth {
  last_event_at: string | null;
  event_count_24h: number;
  last_escalated_at: string | null;
  escalation_count: number;
  escalation_interval_seconds: number;
  next_escalation_in_seconds: number | null;
}

/** Fetch notification chain health */
export async function fetchNotificationChainHealth(): Promise<NotificationChainHealth> {
  const res = await client.get<NotificationChainHealth>('/monitors/chain-health/');
  return res.data;
}

/** Fetch monitor events list */
export async function fetchMonitorEvents(
  params?: Record<string, unknown> & { signal?: AbortSignal },
): Promise<PaginatedResponse<MonitorEvent>> {
  const { signal, ...queryParams } = params || {};
  const res = await client.get<PaginatedResponse<MonitorEvent>>('/monitors/monitor-events/', {
    params: queryParams,
    signal,
  });
  return res.data;
}

/**
 * Acknowledge a monitor event (P-024 alert escalation strategy ).
 * POST /api/monitors/monitor-events/{id}/acknowledge/
 * Backend returns 200 with updated serializer data, or 409 if already acknowledged.
 *
 * @param eventId MonitorEvent id
 * @param note Optional handling note appended to handling_result
 * @returns Updated MonitorEvent payload
 */
export async function acknowledgeEvent(eventId: number, note?: string): Promise<MonitorEvent> {
  const res = await client.post<MonitorEvent>(`/monitors/monitor-events/${eventId}/acknowledge/`, {
    note: note || '',
  });
  return res.data;
}

/** Run system diagnostics */
export async function diagnose(): Promise<{
  overall: string;
  total_issues: number;
  error_count: number;
  warning_count: number;
  fixable_count: number;
  results: Array<{ category: string; status: string; message: string }>;
}> {
  const res = await client.get('/monitors/diagnose/');
  return res.data;
}

/** Auto-fix detected issues */
export async function autoFix(): Promise<{
  success: boolean;
  fixed: Array<{ category: string; message: string }>;
  failed: Array<{ category: string; message: string }>;
}> {
  const res = await client.post('/monitors/fix/');
  return res.data;
}

// ─────────────────────────────────────────────
// Device health grid (Ops > Monitors)
// ─────────────────────────────────────────────

/**
 * Raw device-health item as returned by the backend.
 * Field names are inconsistent (e.g. `cpu` vs `cpu_usage`); consumers map to
 * their own normalized shape via page-specific mappers.
 */
export type DeviceHealthRaw = Record<string, unknown>;

/** Device-health list response — backend may return `devices[]` or `results[]` */
export interface DeviceHealthListResponse {
  devices?: DeviceHealthRaw[];
  results?: DeviceHealthRaw[];
}

/** Fetch device-health list */
export async function fetchDeviceHealth(): Promise<DeviceHealthListResponse> {
  const res = await client.get<DeviceHealthListResponse>('/monitors/device-health/');
  return res.data;
}

// ─────────────────────────────────────────────
// Alert history trend (Ops > Monitors)
// ─────────────────────────────────────────────

/** Alert history single-day data structure */
export interface AlertHistoryDay {
  date: string;
  critical: number;
  warning: number;
  info: number;
  resolved: number;
}

/** Alert history response shape */
export interface AlertHistoryResponse {
  results: AlertHistoryDay[];
}

/** Fetch alert history trend for the given day range (7 / 14 / 30) */
export async function fetchAlertHistory(days: number): Promise<AlertHistoryDay[]> {
  const res = await client.get<AlertHistoryResponse>('/monitors/alerts/history/', {
    params: { days },
  });
  return res.data.results ?? [];
}

// ─────────────────────────────────────────────
// Alert Rule CRUD (from alertRules.ts, merged 2026-08-04)
// ─────────────────────────────────────────────

/** get alert rules list */
export async function fetchAlertRules(params?: { page?: number; page_size?: number }) {
  const res = await client.get('/notifications/alert-rules/', { params });
  return res.data;
}

/** create alert rule */
export async function createAlertRule(data: Partial<AlertRule> & Record<string, unknown>) {
  const res = await client.post('/notifications/alert-rules/', data);
  return res.data;
}

/** update alert rule */
export async function updateAlertRule(id: number, data: Partial<AlertRule> & Record<string, unknown>) {
  const res = await client.patch(`/notifications/alert-rules/${id}/`, data);
  return res.data;
}

/** delete alert rule */
export async function deleteAlertRule(id: number) {
  await client.delete(`/notifications/alert-rules/${id}/`);
}
