/**
 * task domain models (s37 split from models.ts — TD-365).
 */

import type { ScheduleType } from './schedule';
import type { API } from '@/types/api';
export type ExecutionStatus = API.components['schemas']['TaskExecutionStatusEnum'];

/** task step status type — schema reference (spec-29j Phase 2b) */

export type StepStatus = API.components['schemas']['ExecutionStepStatusEnum'];

/**
 * Task execute step — schema reference (spec-29j Phase 2b, 2026-07-19).
 *
 * Migrated from hand-written interface to `API.components['schemas']['TaskStep']`.
 *
 * Schema differences vs the pre-migration hand-written interface:
 *   - `duration`: schema `string | null` (ISO 8601 duration, e.g. "PT1H30M")
 *     vs models was `number | null` (seconds). DRF DurationField serializes
 *     to ISO 8601 string. Consumers that did arithmetic on `duration` now
 *     need a parse step.
 *   - `result_data`: schema `unknown` vs models was `Record<string, unknown> | null`
 *   - `error_message` / `screenshot_path`: schema `string | undefined` vs
 *     models was `string | null`
 *
 * Consumers should treat `duration` as a string, and cast `result_data` to
 * `Record<string, unknown>` at runtime if shape access is required.
 */

export type TaskStep = API.components['schemas']['TaskStep'];

/**
 * Task execute record — schema reference (spec-29j Phase 2b, 2026-07-19).
 *
 * Migrated from hand-written interface to `API.components['schemas']['TaskExecution']`.
 *
 * Schema differences vs the pre-migration hand-written interface:
 *   - `duration`: schema `string | null` (ISO 8601) vs models was `number | null`
 *   - `task`: schema `number | null` (optional) vs models was `number` (required)
 *   - `result_data`: schema `unknown` vs models was `Record<string, unknown> | null`
 *   - `error_message` / `cancel_reason` / `screenshot_path`: schema
 *     `string | undefined` vs models was `string | null`
 *   - `log`: schema optional vs models required
 *
 * Runtime binding display fields (`agent_identifier` / `device_name` /
 * `game_account_username` / `chain_execution_status`) are present in both.
 */

export type TaskExecution = API.components['schemas']['TaskExecution'];

/**
 * Resource pack — schema reference (spec-29j Phase 2c, 2026-07-19).
 *
 * Migrated from hand-written interface to `API.components['schemas']['ResourcePack']`
 * after TD-266 Phase 2b/3a fixed the int count + game_profile_detail
 * schema regressions.
 *
 * Schema differences vs the pre-migration hand-written interface:
 *   - `game_profile_detail`: schema `components['schemas']['GameProfile']`
 *     (nested object, spec-29f Phase 2c fix) vs models was
 *     `GameProfile | null`. Schema is no longer nullable — absent means
 *     `undefined`.
 *   - `config_data`: schema `unknown` vs models was `Record<string, unknown>`.
 *     Consumers needing shape access should cast at runtime.
 *   - `task_count` / `template_count`: schema `number` (spec-29f Phase 2b
 *     fix) vs models was `number` — now consistent.
 *   - Many fields: schema optional vs models required (`description` /
 *     `directory_path` / `is_active` / `created_at`).
 */

export type ResourcePack = API.components['schemas']['ResourcePack'];

/** monitor rule — matches backend MonitorRuleSerializer */

export interface MonitorRule {
  id: number;
  name: string;
  rule_definition: string;
  resource_pack?: number | null;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

/** alert rule — matches backend AlertRule model */

export interface AlertRule {
  id: number;
  name: string;
  rule_type: 'frequency' | 'threshold' | 'pattern';
  threshold?: number;
  pattern?: string;
  notify_methods: string[];
  quiet_start: string | null;
  quiet_end: string | null;
  enabled: boolean;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

/** monitor event severity level — schema reference (spec-29j Phase 2a) */

export type MonitorEventSeverity = API.components['schemas']['SeverityEnum'];

/**
 * Monitor event — schema reference (spec-29j Phase 2a, 2026-07-19).
 *
 * Migrated from hand-written interface to `API.components['schemas']['MonitorEvent']`
 * after TD-266 fixed nested serializer regressions.
 *
 * Schema differences vs the pre-migration hand-written interface:
 *   - `handling_result` / `screenshot_path` / `acknowledged_by_username`:
 *     schema `string | undefined` vs models was `string | null | undefined`
 *   - `event_data`: schema `unknown` vs models was `Record<string, unknown>`
 *   - `severity`: schema optional vs models required
 *
 * Consumers should treat `handling_result` / `screenshot_path` /
 * `acknowledged_by_username` as `string | undefined` (not `string | null`).
 * `event_data` needs a runtime cast to `Record<string, unknown>` if shape
 * access is required.
 */

export type MonitorEvent = API.components['schemas']['MonitorEvent'];

/** Skill definition */

export interface SkillDefinition {
  id: string;
  name: string;
  description: string;
  yaml_content: string;
  version: string;
  applicable_scenarios: string[];
  is_builtin: boolean;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

/** custom task — matches backend CustomTaskSerializer */

export interface CustomTask {
  id: number;
  name: string;
  description: string;
  task_definition: string;
  params_config?: Record<string, unknown>;
  json_schema?: string;
  is_enabled?: boolean;
  created_by?: number;
  created_at: string;
  updated_at: string;
}

/** fixed when task — matches backend ScheduledTaskSerializer */

export interface ScheduledTask {
  id: number;
  task: number;
  custom_task?: number | null;
  schedule_type: ScheduleType;
  cron_expression: string | null;
  scheduled_time?: string | null;
  is_enabled: boolean;
  last_executed_at?: string | null;
  created_by?: number | null;
  created_at: string;
  updated_at: string;
}

/** common paginate request */
