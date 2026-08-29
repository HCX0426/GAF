/**
 * schedule domain models (s37 split from models.ts — TD-365).
 */

export interface TaskStepConfigLegacy {
  id: string;
  name: string;
  action_type: string;
  template_id?: string;
  roi?: string;
  retry_count: number;
  retry_interval: number;
  fallback_action?: string;
  condition?: string;
  next_step?: string;
}

/** task editor mode — spec-2026-07-27-execution-path-unification: chain 已废弃 */

export type TaskEditorMode = 'pipeline' | 'state_machine';

/** fixed when task schedule type — matches backend tasks.ScheduledTask.ScheduleType choices */

export type ScheduleType = 'one_time' | 'periodic';

/** Create scheduled task request — matches backend ScheduledTaskSerializer writeable fields */

export interface CreateScheduledTaskRequest {
  task: number;
  custom_task?: number;
  schedule_type: ScheduleType;
  cron_expression?: string | null;
  scheduled_time?: string;
  is_enabled: boolean;
}

/** notify type — matches backend NotificationSerializer category field */

export type NotificationType = 'info' | 'warning' | 'error' | 'success';

/** notify — matches backend NotificationSerializer */

export interface Notification {
  id: number;
  title: string;
  content: string;
  category: NotificationType;
  is_read: boolean;
  related_url?: string | null;
  created_at: string;
}

/** plugin */

export interface Plugin {
  id: string;
  name: string;
  description: string;
  version: string;
  enabled: boolean;
  installed: boolean;
}

/** AI message role */

export interface TaskFolder {
  id: number;
  owner: number;
  name: string;
  slug: string;
  parent: number | null;
  children: TaskFolder[];
  task_count: number;
  created_at: string;
}

/* ========== Phase 6 scheduler center type ========== */

/** time window */

export interface TimeWindow {
  id: number;
  start_time: string;
  end_time: string;
  days_of_week: number[];
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

/** warmup step */

export interface WarmupStep {
  type: 'start_emulator' | 'start_game' | 'wait_loading' | 'auto_login';
  label: string;
  is_enabled: boolean;
  order: number;
  timeout_seconds: number;
  retry_count: number;
  wait_seconds?: number;
  auto_login?: boolean;
}

/** warmup config */

export interface WarmupConfig {
  id?: number;
  steps: WarmupStep[];
  global_timeout_seconds: number;
  failure_strategy: 'skip_device' | 'retry_then_skip' | 'abort_all';
  created_at?: string;
  updated_at?: string;
}

/** auto stop condition */

export interface AutoStopCondition {
  id: number;
  condition_type:
    | 'consecutive_failures'
    | 'device_offline'
    | 'all_completed'
    | 'window_end'
    | 'manual_stop'
    | 'resource_insufficient';
  is_enabled: boolean;
  threshold?: number | null;
  action: 'stop_all' | 'stop_device' | 'notify_continue';
  created_at: string;
  updated_at: string;
}

/** Cron expression status */

export interface CronExpressionState {
  mode: 'visual' | 'manual';
  visual: {
    minutes: number[];
    hours: number[];
    daysOfMonth: number[];
    months: number[];
    daysOfWeek: number[];
  };
  manual: string;
  humanReadable: string;
  isValid: boolean;
}

/** time window UI status */

export interface TimeWindowUI {
  id: string;
  startTime: string;
  endTime: string;
  daysOfWeek: number[];
  isEnabled: boolean;
}

/** account rotation rules */

export interface AccountRotationRule {
  id?: number;
  name: string;
  strategy: 'sequential' | 'random' | 'by_stamina' | 'by_last_executed';
  accountIds: number[];
  accountOrder: number[];
  switchIntervalSeconds: number;
  autoSkipBlocked: boolean;
  autoSkipCompleted: boolean;
  isActive: boolean;
}

/** execute plan event (spec §2.4.2 — window-centric, based on Device + GameProfile.default_routine) */

export interface ExecutionPlanEvent {
  device_id: number;
  device_name: string;
  account_id: number | null;
  account_name: string | null;
  task_chain_id: number;
  task_chain_name: string;
  /** 0 = today, 1 = tomorrow, ... */
  day_offset: number;
}

/** execute plan response */

export interface ExecutionPlanResponse {
  days: number;
  total_events: number;
  device_count: number;
  account_count: number;
  events: ExecutionPlanEvent[];
}

/** schedule item status */

export type ScheduleItemStatus = 'planned' | 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

/** today schedule item (spec §2.4.2 — derived from execution plan with day_offset=0) */

export interface TodayScheduleItem {
  id: number;
  device_id?: number;
  device_name: string;
  account_id?: number | null;
  account_name: string;
  task_chain_id?: number;
  task_chain_name: string;
  /** scheduled_time is null in the new plan structure (no fixed start time) */
  scheduled_time: string | null;
  actual_start_time?: string | null;
  actual_end_time?: string | null;
  status: ScheduleItemStatus;
  progress?: number;
  error_message?: string | null;
}

/** today schedule response */

export interface TodayScheduleResponse {
  date: string;
  total: number;
  completed: number;
  failed: number;
  items: TodayScheduleItem[];
}

/** switch interval config */

export interface SwitchIntervalConfig {
  accountSwitchSeconds: number;
  taskSwitchSeconds: number;
  deviceSwitchSeconds: number;
}

/** and scheduling slot */

export interface ScheduleSlot {
  id: string;
  accountId: number;
  accountName: string;
  taskId: number;
  taskName: string;
  startOffset: number;
  duration: number;
  color: string;
  priority: number;
}

/** and scheduling */

export interface ConcurrencySchedule {
  deviceId: number;
  deviceName: string;
  slots: ScheduleSlot[];
}

/** ── Phase 8: unattended type definition ── */

/** unattended session status
 *
 * P-011 multi-session parallel: each UnattendedSession is scoped to a
 * GameProfile. Multiple sessions may run concurrently as long as their
 * game_profile differs. The frontend store keeps an array of these.
 *
 * `id` is null for the default/empty session placeholder used before any
 * backend session has been created. Once a session is started, the backend
 * returns its numeric id and the store replaces the placeholder.
 */

export interface UnattendedSession {
  id: number | null;
  /** FK to GameProfile (P-011). null = legacy/unknown scope. */
  gameProfileId: number | null;
  /** GameProfile.game_name snapshot for display (P-011). */
  gameProfileName: string | null;
  isRunning: boolean;
  isPaused: boolean;
  startedAt: string | null;
  stoppedAt: string | null;
  stopReason: string | null;
  /** loop rotation: return accounts to pool and keep dispatching once the
   * account chain completes (backend UnattendedSession.loop_rotation). */
  loopRotation?: boolean;
}

/** pre-check list single item */

export interface PreflightCheck {
  check_type: 'device_online' | 'account_valid' | 'resource_ready' | 'agent_connection' | 'scheduler_rules';
  status: 'pass' | 'fail' | 'warning';
  message: string;
  fix_action?: string;
}

/** matrix cell status */
