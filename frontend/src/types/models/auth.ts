/**
 * auth domain models (s37 split from models.ts — TD-365).
 */

import type { API } from '@/types/api';
export type User = API.components['schemas']['User'];

/** login request param */

export interface LoginRequest {
  username: string;
  password: string;
  remember_me?: boolean;
}

/** login response data */

export interface LoginResponse {
  access: string;
  refresh: string;
  must_change_password: boolean;
  /**
   * Authenticated user. Extends `User` with `is_first_login`, which the
   * backend (`CustomTokenObtainPairSerializer.validate`) computes from
   * `user.last_login is None` and attaches to the response `user` dict at
   * runtime. Not part of the `UserSerializer` schema, so it is modeled
   * here as an optional extension rather than on `User` itself.
   */
  user: User & { is_first_login?: boolean };
  requires_2fa?: boolean;
  temp_token?: string;
}

/** Token refresh response */

export interface RefreshTokenResponse {
  access: string;
  refresh?: string;
}

/** system initial start transform status */

export interface InitStatus {
  initialized: boolean;
  has_admin: boolean;
  default_user_exists: boolean;
  register_enabled: boolean;
}

/** change password request */

export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}

/** Agent status type — matches backend Agent.Status choices */

export type AgentStatus = API.components['schemas']['AgentHeartbeatStatusEnum'];

/**
 * Agent info — schema reference (spec-29j Phase 2a, 2026-07-19).
 *
 * Migrated from hand-written interface to `API.components['schemas']['Agent']`
 * after TD-266 Phase 1 fixed the `capabilities: JSONField` schema regression.
 *
 * Schema differences vs the pre-migration hand-written interface:
 *   - `ip_address`: schema `string | null` (optional) vs models was `string` (required)
 *   - `os_info` / `status` / `cpu_usage` / `memory_usage` / `screenshot_fps` /
 *     `capabilities`: schema optional vs models required
 *
 * Consumers should treat all fields as potentially undefined and use
 * optional chaining / nullish coalescing when accessing them.
 */

export type Agent = API.components['schemas']['Agent'];

/**
 * Task definition — schema reference (spec-29j Phase 2c, 2026-07-19).
 *
 * Migrated from hand-written interface to `API.components['schemas']['Task']`
 * after TD-266 Phase 2 fixed the int count + nested serializer regressions.
 *
 * Schema differences vs the pre-migration hand-written interface:
 *   - `game_accounts` / `devices`: schema absent (write_only
 *     PrimaryKeyRelatedField / ListField) vs models had them as optional
 *     arrays. **Pre-existing bug**: TaskFormModal read `editingTask.
 *     game_accounts?.map((ga) => ga.id)` to backfill the form, but the
 *     backend never returned these fields in read responses (only
 *     `game_account_details` / `device_details`). Fixed in the same
 *     migration: TaskFormModal now reads `game_account_details` /
 *     `device_details`.
 *   - `game_account` / `game_account_name` / `source_type_display` /
 *     `resource_pack`: schema absent vs models had them. These were
 *     pre-existing dead code — the backend TaskSerializer never returned
 *     these fields. TaskDetailDrawer references removed in the same
 *     migration.
 *   - `tags`: schema `unknown` (DRF Spectacular cannot infer TaggableManager
 *     type) vs models `string[]`. Cast at runtime: `(task.tags ?? []) as
 *     string[]`.
 *   - `task_definition` / `params_config` / `retry_policy` /
 *     `preflight_config` / `recovery_config` / `success_criteria`: schema
 *     `unknown` (JSONField) vs models `Record<string, unknown>`. Cast at
 *     runtime when shape access is required.
 *   - `game_account_details` / `device_details` / `game_profile_detail`:
 *     schema nested objects (spec-29f Phase 2a fix) vs models hand-written
 *     inline types. Schema is now the source of truth.
 *   - `device_count` / `account_count`: schema `number` (spec-29f Phase 2b
 *     fix) vs models `number` — now consistent.
 *   - `source_type`: schema `SourceTypeEnum` vs models `'manual' |
 *     'yaml_import'`. Same string literal union — equivalent.
 *   - `execution_mode`: schema `ExecutionModeEnum` vs models `string`.
 *     Schema is more precise.
 *   - Many fields: schema optional vs models required (`name` /
 *     `created_at` / `updated_at`). Consumers should use optional chaining.
 */

export type Task = API.components['schemas']['Task'];

/** task execute status type — schema reference (spec-29j Phase 2b) */

export interface TOTPSetupResponse {
  secret: string;
  otp_uri: string;
}

/** 2FA status */

export interface TOTPStatus {
  enabled: boolean;
}

/** 2FA login step 2 request */

export interface Login2FARequest {
  temp_token: string;
  totp_code: string;
  remember_me?: boolean;
}

/** user session ( login device ) */

export interface UserSession {
  id: number;
  device_name: string;
  device_type: 'web' | 'mobile' | 'desktop' | 'api' | 'unknown';
  ip_address: string | null;
  location: string;
  last_activity: string;
  created_at: string;
  expires_at: string;
  is_active: boolean;
  is_current: boolean;
}

/** login history (M4 audit trail ) */

export interface LoginHistory {
  id: number;
  user: number;
  username: string;
  ip_address: string;
  user_agent: string;
  location: string;
  created_at: string;
}

/** account group */

export interface AccountGroup {
  id: number;
  owner: number;
  name: string;
  slug: string;
  account_count: number;
  created_at: string;
}

/** account rotation rules */

export interface RotationRule {
  id: number;
  name: string;
  rotation_strategy: 'sequential' | 'random' | 'by_stamina' | 'by_last_executed';
  accounts: number[];
  account_details?: { id: number; username: string; game_name: string }[];
  switch_interval_seconds: number;
  auto_skip_blocked: boolean;
  is_active: boolean;
  owner: number;
  created_at: string;
}

/** task device mapping (TaskDevice) */

export interface TaskDeviceMapping {
  id: number;
  device: number;
  device_name: string;
  task: number;
  is_default: boolean;
  created_at: string;
}

/** account binding info */

export interface AccountBindingInfo {
  account_ids: number[];
  accounts: Array<{ id: number; game_name: string; username: string; status: string }>;
  rotation_rule_id: number | null;
  rotation_rule: string | null;
}

/** batch operations result */

export interface BulkActionResult {
  action: string;
  affected: number;
  message: string;
  tasks?: Record<string, unknown>[];
}

/** task file folder */
