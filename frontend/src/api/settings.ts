/**
 * system settings related API
 * includes user management, app config interfaces
 */
import client from './client';
import type { User, LlmConfig, AppSettings, PaginatedResponse, PaginationParams } from '@/types/models';

/** get user list */
export async function fetchUsers(params?: PaginationParams): Promise<PaginatedResponse<User>> {
  const res = await client.get<PaginatedResponse<User>>('/accounts/users/', { params });
  return res.data;
}

/** create user */
export async function createUser(data: { username: string; password: string; role: string }): Promise<User> {
  const res = await client.post<User>('/accounts/users/', data);
  return res.data;
}

/** update user */
export async function updateUser(userId: number, data: Partial<User>): Promise<User> {
  const res = await client.put<User>(`/accounts/users/${userId}/`, data);
  return res.data;
}

/** delete user */
export async function deleteUser(userId: number): Promise<void> {
  await client.delete(`/accounts/users/${userId}/`);
}

/** admin reset user password */
export async function resetUserPassword(userId: number): Promise<{ new_password: string }> {
  const res = await client.post<{ new_password: string }>(`/accounts/users/${userId}/reset-password/`);
  return res.data;
}

/** get LLM config */
export async function fetchLlmConfig(): Promise<LlmConfig> {
  const res = await client.get<AppSettings[]>('/settings/app-settings/', {
    params: { search: 'llm_config' },
  });
  const items = (res.data as unknown as { results?: AppSettings[] }).results ?? (res.data as unknown as AppSettings[]);
  const found = Array.isArray(items) ? items.find((s: AppSettings) => s.setting_key === 'llm_config') : null;
  if (!found) throw new Error('LLM config not found');
  return found.setting_value as unknown as LlmConfig;
}

/** update LLM config */
export async function updateLlmConfig(data: Partial<LlmConfig>): Promise<LlmConfig> {
  const existing = await fetchLlmConfig().catch(() => null);
  const llmSettings = await client.get<{ results: AppSettings[] }>('/settings/app-settings/', {
    params: { search: 'llm_config' },
  });
  const found = llmSettings.data.results?.find((s) => s.setting_key === 'llm_config');
  if (!found) throw new Error('LLM config setting not found');
  const merged = { ...(existing ?? {}), ...data };
  const res = await client.put<AppSettings>(`/settings/app-settings/${found.id}/`, {
    setting_value: merged,
  });
  return res.data.setting_value as unknown as LlmConfig;
}

/** get system config list */
export async function fetchSystemConfigs(): Promise<AppSettings[]> {
  const res = await client.get<PaginatedResponse<AppSettings>>('/settings/app-settings/');
  return res.data.results;
}

/** update system config */
export async function updateSystemConfig(key: string, value: string): Promise<AppSettings> {
  const all = await client.get<PaginatedResponse<AppSettings>>('/settings/app-settings/', {
    params: { search: key },
  });
  const found = all.data.results?.find((s) => s.setting_key === key);
  if (!found) throw new Error(`AppSetting with key="${key}" not found`);
  const res = await client.put<AppSettings>(`/settings/app-settings/${found.id}/`, {
    setting_value: value,
  });
  return res.data;
}

/** Config Generator field type */
export interface ConfigField {
  key: string;
  label: string;
  type: string;
  default_value?: unknown;
  required: boolean;
  options: Array<{ label: string; value: unknown }>;
  placeholder: string;
  help_text: string;
  validation: Record<string, unknown>;
  group: string;
  visible: boolean;
  disabled: boolean;
  order: number;
}

/** Config schema response */
export interface ConfigSchemaResponse {
  success: boolean;
  schema: {
    version: number;
    task_type: string;
    fields: Array<Record<string, unknown>>;
    metadata: Record<string, unknown>;
  };
  fields: ConfigField[];
}

/** Get form schema for a task type */
export async function fetchConfigSchema(taskType: string = 'general'): Promise<ConfigSchemaResponse> {
  const res = await client.get<ConfigSchemaResponse>('/settings/config-generator/', {
    params: { action: 'schema', task_type: taskType },
  });
  return res.data;
}

/** Validate config values against schema */
export async function validateConfigValues(
  values: Record<string, unknown>,
  taskType: string = 'general',
): Promise<{ success: boolean; errors: string[] }> {
  const res = await client.post<{ success: boolean; errors: string[] }>('/settings/config-generator/', {
    action: 'validate',
    values,
    task_type: taskType,
  });
  return res.data;
}

/** Export config values as structured dict */
export async function exportConfig(
  values: Record<string, unknown>,
  taskType: string = 'general',
): Promise<{ success: boolean; config: Record<string, unknown> }> {
  const res = await client.post<{ success: boolean; config: Record<string, unknown> }>('/settings/config-generator/', {
    action: 'export',
    values,
    task_type: taskType,
  });
  return res.data;
}

/** Import config dict and fill defaults */
export async function importConfig(
  config: Record<string, unknown>,
): Promise<{ success: boolean; values: Record<string, unknown>; task_type: string }> {
  const res = await client.post<{ success: boolean; values: Record<string, unknown>; task_type: string }>(
    '/settings/config-generator/',
    { action: 'import', config },
  );
  return res.data;
}

/** List available task types */
export async function fetchConfigTaskTypes(): Promise<{
  success: boolean;
  task_types: Record<string, { field_count: number | { error: string } }>;
}> {
  const res = await client.get('/settings/config-generator/', {
    params: { action: 'task-types' },
  });
  return res.data;
}

// ============================================================
// Config Migration API (Alas-style chained migration)
// ============================================================

/** Migration system info returned by GET /config-migration/ */
export interface MigrationInfo {
  success: boolean;
  latest_version: number;
  available_versions: number[];
  version_descriptions: Record<string, string>;
}

/** Detect version response */
export interface DetectVersionResponse {
  success: boolean;
  detected_version: number;
  method: 'explicit' | 'heuristic' | 'default';
  latest_version: number;
  needs_migration: boolean;
}

/** Single migration log entry */
export interface MigrationLogEntry {
  timestamp: string;
  from_version: number;
  to_version: number;
  changed_keys: string[];
}

/** Migrate response */
export interface MigrateConfigResponse {
  success: boolean;
  migrated_config: Record<string, unknown>;
  from_version: number;
  to_version: number;
  migration_log: MigrationLogEntry[];
  message?: string;
}

/** Get migration system info (latest version + available versions + descriptions) */
export async function fetchMigrationInfo(): Promise<MigrationInfo> {
  const res = await client.get<MigrationInfo>('/settings/config-migration/');
  return res.data;
}

/** Detect config version (explicit __config_version__ + heuristic fallback) */
export async function detectConfigVersion(config: Record<string, unknown>): Promise<DetectVersionResponse> {
  const res = await client.post<DetectVersionResponse>('/settings/config-migration/', { action: 'detect', config });
  return res.data;
}

/** Migrate config from detected/explicit version to target version (default: latest) */
export async function migrateConfig(
  config: Record<string, unknown>,
  options?: { from_ver?: number; to_ver?: number },
): Promise<MigrateConfigResponse> {
  const body: Record<string, unknown> = { action: 'migrate', config };
  if (options?.from_ver !== undefined) body.from_ver = options.from_ver;
  if (options?.to_ver !== undefined) body.to_ver = options.to_ver;
  const res = await client.post<MigrateConfigResponse>('/settings/config-migration/', body);
  return res.data;
}

// ============================================================
// System maintenance API (data cleanup, task stats, diagnostic pack)
// ============================================================

/** Per-task stats entry returned by /analytics/task-stats/ (list) */
export interface TaskStatsItem {
  task_id: number;
  task_name: string;
  total_executions: number;
  success_rate: number;
}

/** Task statistics returned by /analytics/task-stats/ (per-task list) */
export interface TaskStats {
  total_executions: number;
  total_screenshots: number;
  total_logs: number;
}

/** Cleanup request body for /settings/cleanup/ */
export interface CleanupParams {
  execution_retention_days: number;
  screenshot_retention_gb: number;
  log_retention_days: number;
}

/**
 * Fetch aggregate task statistics.
 *
 * Endpoint belongs to the analytics domain; co-located here because no
 * dedicated analytics API module exists yet. Consumed by the System
 * Settings data-cleanup tab.
 */
export async function fetchTaskStats(config?: { signal?: AbortSignal }): Promise<TaskStats> {
  // /analytics/task-stats/ returns a per-task list {results: [...]}; aggregate
  // total executions for the cleanup page. Screenshot/log totals have no
  // backend aggregation — report 0 rather than a misleading "-".
  const res = await client.get<{ results?: TaskStatsItem[] }>('/analytics/task-stats/', config);
  const tasks = res.data.results ?? [];
  return {
    total_executions: tasks.reduce((s, t) => s + (t.total_executions ?? 0), 0),
    total_screenshots: 0,
    total_logs: 0,
  };
}

/** Run data cleanup with the given retention policy */
export async function cleanupData(params: CleanupParams): Promise<void> {
  await client.post('/settings/cleanup/', params);
}

/** Generate a diagnostic pack and return it as a Blob (zip download) */
export async function generateDiagnosticPack(): Promise<Blob> {
  const res = await client.post<Blob>('/settings/diagnostic/', null, { responseType: 'blob' });
  return res.data;
}

// ============================================================
// Agent Debug Mode API (singleton upsert via /settings/agent-debug/)
// ============================================================

/** Agent debug mode config stored as AppSettings(agent_debug). */
export interface AgentDebugConfig {
  /** Whether to save annotated screenshots during pipeline execution. */
  enabled: boolean;
  /** Directory under repo root where debug images are organized. */
  dir: string;
}

const DEFAULT_AGENT_DEBUG: AgentDebugConfig = { enabled: false, dir: 'debug' };

/** Fetch the current agent debug mode config (singleton upsert endpoint). */
export async function fetchAgentDebug(): Promise<AgentDebugConfig> {
  const res = await client.get<AgentDebugConfig>('/settings/agent-debug/');
  // Merge with defaults to ensure both fields are present
  return { ...DEFAULT_AGENT_DEBUG, ...res.data };
}

/** Update the agent debug mode config (POST = upsert, no id needed). */
export async function updateAgentDebug(config: AgentDebugConfig): Promise<AgentDebugConfig> {
  const res = await client.post<AgentDebugConfig>('/settings/agent-debug/', {
    enabled: config.enabled,
    dir: config.dir || 'debug',
  });
  return { ...DEFAULT_AGENT_DEBUG, ...res.data };
}

// ============================================================
// Window Background Wait API (singleton upsert via /settings/wait-when-background/)
// ============================================================

/**
 * Window background wait config stored as AppSettings(wait_when_background).
 *
 * When enabled, the agent monitors the target window's foreground state during
 * pipeline execution. If the window loses foreground (user alt-tabs away),
 * the pipeline is paused; when the window regains foreground, the pipeline
 * resumes. If the pause exceeds timeout_seconds, the pipeline is cancelled.
 */
export interface WindowBackgroundWaitConfig {
  /** Whether to pause pipeline when target window loses foreground. */
  enabled: boolean;
  /** Max seconds to wait in background before cancelling (0 = infinite). */
  timeout_seconds: number;
  /** Polling interval in milliseconds for foreground check. */
  check_interval_ms: number;
}

const DEFAULT_WINDOW_BACKGROUND_WAIT: WindowBackgroundWaitConfig = {
  enabled: false,
  timeout_seconds: 1800,
  check_interval_ms: 500,
};

/** Fetch the current window background wait config (singleton upsert endpoint). */
export async function fetchWindowBackgroundWait(): Promise<WindowBackgroundWaitConfig> {
  const res = await client.get<WindowBackgroundWaitConfig>('/settings/wait-when-background/');
  return { ...DEFAULT_WINDOW_BACKGROUND_WAIT, ...res.data };
}

/** Update the window background wait config (POST = upsert, no id needed). */
export async function updateWindowBackgroundWait(
  config: WindowBackgroundWaitConfig,
): Promise<WindowBackgroundWaitConfig> {
  const res = await client.post<WindowBackgroundWaitConfig>('/settings/wait-when-background/', {
    enabled: config.enabled,
    timeout_seconds: config.timeout_seconds,
    check_interval_ms: config.check_interval_ms,
  });
  return { ...DEFAULT_WINDOW_BACKGROUND_WAIT, ...res.data };
}

// ============================================================
// FeatureFlag API (multi-game mode toggle, Spec A)
// ============================================================

/** FeatureFlag row shape returned by /settings/feature-flags/. */
export interface FeatureFlag {
  id: number;
  name: string;
  description: string;
  enabled: boolean;
  rollout_percentage: number;
  allowed_roles: string[] | null;
  allowed_ips: string[] | null;
}

/**
 * Fetch a FeatureFlag by exact name.
 *
 * Uses the `search` filter (backed by DRF SearchFilter on `name` + `description`)
 * then matches exactly on `name` to avoid partial-match surprises.
 */
export async function fetchFeatureFlagByName(name: string): Promise<FeatureFlag | null> {
  const res = await client.get<{ results: FeatureFlag[] } | FeatureFlag[]>('/settings/feature-flags/', {
    params: { search: name },
  });
  const list = (res.data as { results?: FeatureFlag[] }).results ?? (res.data as FeatureFlag[]);
  return list.find((f) => f.name === name) ?? null;
}

/** Update the `enabled` field of a FeatureFlag by id. */
export async function patchFeatureFlag(id: number, patch: { enabled: boolean }): Promise<FeatureFlag> {
  const res = await client.patch<FeatureFlag>(`/settings/feature-flags/${id}/`, patch);
  return res.data;
}

/**
 * Canonical flag name for the multi-game parallel mode toggle (Spec A).
 * Must match backend/settings/feature_flags.py:MULTI_GAME_MODE_FLAG.
 */
export const MULTI_GAME_MODE_FLAG = 'unattended_multi_game_mode';

/** Convenience: read the multi-game mode flag (false if not seeded yet). */
export async function fetchMultiGameMode(): Promise<boolean> {
  const flag = await fetchFeatureFlagByName(MULTI_GAME_MODE_FLAG);
  return flag?.enabled ?? false;
}

/** Convenience: toggle the multi-game mode flag. */
export async function updateMultiGameMode(enabled: boolean): Promise<void> {
  const flag = await fetchFeatureFlagByName(MULTI_GAME_MODE_FLAG);
  if (!flag) {
    throw new Error(`FeatureFlag "${MULTI_GAME_MODE_FLAG}" not found. Run migration settings/0007.`);
  }
  await patchFeatureFlag(flag.id, { enabled });
}
