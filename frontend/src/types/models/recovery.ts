/**
 * recovery domain models (s37 split from models.ts — TD-365).
 */

export interface RecoveryConfig {
  max_retries: number;
  retry_interval_seconds: number;
  exponential_backoff: boolean;
}

/** task level recover config */

export interface TaskRecoveryConfig {
  consecutive_failure_threshold: number;
  on_threshold_action: string;
}

/** app level recover config */

export interface AppRecoveryConfig {
  game_freeze_detection: boolean;
  freeze_timeout_seconds: number;
  on_freeze_action: string;
}

/** device level recover config */

export interface DeviceRecoveryConfig {
  crash_detection: boolean;
  on_crash_action: string;
  backup_device_id: string;
  max_reboot_count: number;
}

/** system level recover config */

export interface SystemRecoveryConfig {
  agent_no_response_timeout: number;
  on_no_response_actions: string[];
}

/** night mode config */

export interface NightModeConfig {
  enabled: boolean;
  low_power_hours: [string, string];
  screenshot_interval_multiplier: number;
  operation_interval_multiplier: number;
  cpu_throttle: boolean;
  auto_pause_non_critical: boolean;
}

/** frequency limit config */

export interface FrequencyLimitConfig {
  max_per_account_per_day: number;
  max_global_per_day: number;
  min_interval_per_task: number;
  mode: string;
}

/** notify strategy config */

export interface NotificationPolicyConfig {
  enabled_events: string[];
}

/** cooldown config */

export interface CooldownConfig {
  emulator_reboot_cooldown: number;
  game_restart_cooldown: number;
  consecutive_login_cooldown: number;
  recovery_cooldown: number;
}

/** unattended strategy */

export interface UnattendedStrategy {
  id: number;
  recovery_config: RecoveryConfig;
  task_recovery_config: TaskRecoveryConfig;
  app_recovery_config: AppRecoveryConfig;
  device_recovery_config: DeviceRecoveryConfig;
  system_recovery_config: SystemRecoveryConfig;
  night_mode_config: NightModeConfig;
  frequency_limit_config: FrequencyLimitConfig;
  notification_policy: NotificationPolicyConfig;
  cooldown_config: CooldownConfig;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** app config */

export interface AppSettings {
  id: number;
  setting_key: string;
  setting_value: Record<string, unknown>;
  category: string;
  description: string;
  updated_by: number | null;
  created_at: string;
  updated_at: string;
}

// L11+L12: duplicate InitStatus removed — use the canonical definition above
// (which includes register_enabled). Previously this duplicate was missing
// register_enabled, causing type inconsistency.

/** initial start transform settings request */

export interface SetupRequest {
  admin_username: string;
  admin_password: string;
  device_type: 'windows' | 'emulator' | 'both';
  llm_config?: {
    api_key?: string;
    model?: string;
    provider?: string;
    api_base?: string;
    temperature?: number;
    max_tokens?: number;
  };
}

/** debug log analysis status */
