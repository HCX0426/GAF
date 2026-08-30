/**
 * Ops domain misc API
 * Covers backup, analytics, SLA dashboard, and other Ops-specific endpoints
 * that don't fit in monitors.ts / executions.ts / scheduler.ts.
 */
import client from './client';

// ─────────────────────────────────────────────
// SLA dashboard
// ─────────────────────────────────────────────

/** SLA metric record item.

 * Field names follow the backend metrics app (Prometheus/OpenMetrics
 * convention: `value` / `labels` / `timestamp`). The previous duplicate
 * in the tasks app used `metric_value` / `tags` / `recorded_at`; those
 * were removed in TD-021 Stage 6 Task 17 and the frontend was migrated
 * to the canonical `/api/v2/metrics/sla/` endpoint.
 */
export interface SlaMetric {
  id: number;
  metric_name: string;
  value: number;
  labels?: Record<string, unknown>;
  timestamp: string;
  agent?: number | null;
  agent_name?: string | null;
}

/** SLA metrics list response — backend may return array or paginated shape */
export interface SlaMetricsResponse {
  results?: SlaMetric[];
  [key: string]: unknown;
}

/**
 * Fetch SLA metric records.
 * Backend may return either a plain array or a paginated `{ results: [...] }`
 * payload; this function normalizes to a flat array.
 */
export async function fetchSlaMetrics(): Promise<SlaMetric[]> {
  // Backend: SLAMetricViewSet lives under the monitors app — /monitors/sla/ —
  // after the metrics app was merged into monitors (2026-08-04). The old
  // /metrics/sla/ path returns 404.
  const res = await client.get<SlaMetric[] | SlaMetricsResponse>('/monitors/sla/');
  const data = res.data;
  return Array.isArray(data) ? data : data.results || [];
}

// ─────────────────────────────────────────────
// Analytics dashboard
// ─────────────────────────────────────────────

/** Step elapsed-time ranking item */
export interface StepHeatItem {
  step_type: string;
  avg_duration_ms: number;
  execution_count: number;
}

/** Daily trend entry — matches backend /analytics/trend/ */
export interface TrendItem {
  date: string;
  execution_count: number;
  success_rate: number;
  avg_duration: number;
}

/** Weekly report data */
export interface WeeklyReport {
  total_executions: number;
  success_count: number;
  failed_count: number;
  most_executed_task: string;
  avg_step_duration_ms: number;
  success_rate: number;
  recovery_triggered_count: number;
  avg_recovery_attempts: number;
  recovery_success_rate: number | null;
}

/** Worker performance record item */
export interface WorkerPerfItem {
  agent_name: string;
  execution_count: number;
  success_rate: number;
  avg_duration_ms: number;
}

/** Fetch step elapsed-time heatmap ranking */
export async function fetchStepHeatmap(): Promise<StepHeatItem[]> {
  const res = await client.get<StepHeatItem[]>('/analytics/step-heatmap/');
  return res.data;
}

/** Fetch execution trend over time */
export async function fetchAnalyticsTrend(): Promise<TrendItem[]> {
  const res = await client.get<{ trend: TrendItem[] }>('/analytics/trend/');
  return res.data.trend ?? [];
}

/** Fetch weekly execution report */
export async function fetchWeeklyReport(): Promise<WeeklyReport> {
  const res = await client.get<WeeklyReport>('/analytics/weekly-report/');
  return res.data;
}

/** Fetch worker performance comparison */
export async function fetchWorkerPerformance(): Promise<WorkerPerfItem[]> {
  const res = await client.get<WorkerPerfItem[]>('/analytics/agent-performance/');
  return res.data;
}

// ─────────────────────────────────────────────
// Backup / restore
// ─────────────────────────────────────────────

/**
 * Create a full backup archive.
 * Returns a ZIP blob for browser download.
 */
export async function createBackup(): Promise<Blob> {
  const res = await client.post<Blob>('/tasks/backup/create/', null, { responseType: 'blob' });
  return res.data;
}

/**
 * Restore from an uploaded backup file.
 * Sends multipart/form-data with the file under the `file` field.
 */
export async function restoreBackup(file: File): Promise<void> {
  const formData = new FormData();
  formData.append('file', file);
  await client.post('/tasks/backup/restore/', formData);
}

// ─────────────────────────────────────────────
// Crash report actions
// (read-only listing lives in logs.ts:fetchCrashReports; this module owns the
// write-side PATCH endpoint which debug.ts does not expose.)
// ─────────────────────────────────────────────

/** Payload for resolving a crash report */
export interface ResolveCrashReportPayload {
  resolved: boolean;
}

/**
 * Mark a crash report as resolved (or unresolved).
 * PATCH /debug/crash-reports/{id}/
 */
export async function resolveCrashReport(id: number, payload: ResolveCrashReportPayload): Promise<void> {
  await client.patch(`/debug/crash-reports/${id}/`, payload);
}
