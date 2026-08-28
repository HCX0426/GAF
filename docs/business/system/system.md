---
summary: 系统设置 — 无人值守策略 / LLM 配置 / 功能开关 / 调试日志 / 插件 / 审计
applies_to: ['backend', 'frontend', 'design']
key_decisions:
  - settings app 4 模型 + debug app 4 模型, 共 8 个数据模型
  - UnattendedStrategy 单例模式, 5 层恢复策略 + 夜间模式 + 频率限制 + 通知策略 + 冷却
  - LLMConfig api_key AES 加密存储, 响应仅返回 masked 预览
  - FeatureFlag 支持灰度百分比 + 角色白名单 + IP 白名单
  - AppSettings KV 存储, agent_debug / wait_when_background 存于此
last_updated: 2026-07-29
---

# 系统设置

> 模块路由 `/system/*`，对应前端侧边栏"系统"。覆盖系统配置、无人值守策略、LLM 配置、功能开关、插件、API Key、审计日志、调试日志归档。

## 1. 数据模型

### 1.1 settings app

文件：[settings/models.py](file:///d:/code/GAF/backend/settings/models.py)

#### UnattendedStrategy（无人值守策略，单例）
db_table: `settings_unattended_strategy`

| 字段 | 类型 | 用途 |
|---|---|---|
| `recovery_config` | JSONField | 5 层恢复策略（见 §2.1） |
| `night_mode_config` | JSONField | 夜间模式时段与限制 |
| `frequency_limit_config` | JSONField | 执行频率限制 |
| `notification_policy` | JSONField | 告警通知策略 |
| `cooldown_config` | JSONField | 任务冷却时间 |
| `is_active` | Bool | 是否启用 |

#### LLMConfig（LLM 配置，单例）
- `provider`: `openai` / `deepseek` / `ollama` / `custom`
- `api_key`: 存储时 AES 加密（`gAAAAA` 前缀避免重复加密）
- `api_base` / `default_model` / `temperature` / `max_tokens`
- `save()` 自动加密；`get_api_key()` 返回明文

#### FeatureFlag（功能开关）
- `name` (unique) / `description` / `enabled` / `rollout_percentage` (0-100 灰度)
- `allowed_roles` (JSON list) / `allowed_ips` (JSON list)

#### AppSettings（KV 配置存储）
- `setting_key` (unique) / `setting_value` (JSONField) / `category` / `description`
- 已知键：`agent_debug`（`{enabled, dir}`）/ `wait_when_background`（`{enabled, timeout_seconds, check_interval_ms}`）

### 1.2 debug app

文件：[debug/models.py](file:///d:/code/GAF/backend/debug/models.py)

| 模型 | 用途 |
|---|---|
| `DebugLogArchive` | 调试日志 ZIP 归档，`analysis_status`: pending/analyzing/completed |
| `LLMAnalysisResult` | LLM 分析结果，`review_status`: pending/adopted/ignored/investigating |
| `BackupRecord` | 备份记录，`includes` (JSON) + `is_auto` |
| `CrashReport` | 崩溃报告，`component` / `error_type` / `stack_trace` / `resolved` |

## 2. 无人值守策略配置

### 2.1 5 层恢复策略（recovery_config）

详见 [settings/serializers.py](file:///d:/code/GAF/backend/settings/serializers.py)。

| 层级 | 字段 | 默认值 | 范围 |
|---|---|---|---|
| **stepLevel** | `maxRetries` | 3 | 0-100 |
|  | `retryIntervalSeconds` | 5 | 0-3600 |
|  | `exponentialBackoff` | false | — |
| **taskLevel** | `consecutiveFailureThreshold` | 3 | 1-100 |
|  | `failureAction` | `skip` | skip/restart/switch_account |
| **appLevel** | `freezeDetection` | true | — |
|  | `freezeTimeoutSeconds` | 120 | 10-3600 |
|  | `freezeAction` | `restart_app` | restart_app/relogin/notify_only |
| **deviceLevel** | `crashDetection` | true | — |
|  | `crashAction` | `restart_emulator` | restart_emulator/reconnect_adb/switch_backup |
|  | `backupDeviceId` | null | — |
|  | `maxRestartCount` | 2 | 0-100 |
| **systemLevel** | `agentTimeoutSeconds` | 300 | 30-7200 |
|  | `timeoutActions` | `['notify','mark_offline','reassign']` | 子集 |

恢复引擎实现见 [scheduler/recovery_engine.py](file:///d:/code/GAF/backend/scheduler/recovery_engine.py)，调度逻辑见 [business/ops/scheduler.md](../ops/scheduler.md)。

### 2.2 夜间模式（night_mode_config）
| 字段 | 默认值 |
|---|---|
| `isEnabled` | false |
| `timeRange` | `{start: '00:00', end: '06:00'}` |
| `screenshotIntervalMultiplier` | 2 (1-10) |
| `operationIntervalMultiplier` | 2 (1-5) |
| `cpuThrottle` | true |
| `autoPauseNonCritical` | false |

### 2.3 频率限制（frequency_limit_config）
| 字段 | 默认值 | 范围 |
|---|---|---|
| `maxPerAccountPerDay` | 10 | 1-99 |
| `maxGlobalPerDay` | 100 | 1-999 |
| `minTaskIntervalSeconds` | 30 | 0-3600 |
| `mode` | `fixed` | fixed/adaptive |
| `todayExecuted` / `todayLimit` | 0 / 100 | read_only |

### 2.4 通知策略（notification_policy）
- `enabledEvents` 默认: `['task_failed', 'device_offline', 'account_blocked', 'game_updated', 'auto_stop_triggered', 'recovery_triggered']`
- 可选值: task_failed / device_offline / account_blocked / game_updated / consecutive_failures / auto_stop_triggered / night_mode_switch / resource_expiring / recovery_triggered / daily_report_generated

### 2.5 冷却时间（cooldown_config）
| 字段 | 默认值 | 范围 |
|---|---|---|
| `emulatorRestartSeconds` | 120 | 60-600 |
| `gameRestartSeconds` | 60 | 30-300 |
| `consecutiveLoginSeconds` | 10 | 5-120 |
| `recoveryPauseSeconds` | 180 | 60-600 |

## 3. API 端点

### 3.1 settings app
前缀 `/api/v2/settings/`，详见 [settings/urls.py](file:///d:/code/GAF/backend/settings/urls.py)。

| 路径 | 方法 | 用途 |
|---|---|---|
| `llm-config/` | CRUD | LLM 配置（api_key write_only + 返回 api_key_masked） |
| `feature-flags/` | CRUD | 功能开关（仅 manage 角色） |
| `app-settings/` | CRUD | KV 配置（自动写 updated_by） |
| `unattended-strategy/` | GET/POST | 无人值守策略 Upsert（写审计 UNATTENDED_STRATEGY） |
| `agent-debug/` | GET/POST | Agent debug 模式（存 AppSettings `agent_debug`） |
| `wait-when-background/` | GET/POST | 窗口后台等待配置 |
| `diagnostic/` | POST | 生成诊断 ZIP |
| `cleanup/` | POST | 数据清理（仅 manage） |
| `config-generator/` | GET/POST | action: schema/validate/export/import/task-types |
| `config-migration/` | GET/POST | action: detect/migrate（Alas-style 链式迁移） |

### 3.2 debug app
前缀 `/api/v2/debug/`，详见 [debug/urls.py](file:///d:/code/GAF/backend/debug/urls.py)。

| 路径 | 用途 |
|---|---|
| `crash-reports/` | 崩溃报告 CRUD |
| `debug-logs/` | 日志归档 CRUD（multipart 上传） |
| `debug-logs/<pk>/analyze/` | POST 发起 LLM 分析（异步 Celery） |
| `analysis-results/` | 分析结果只读列表 |
| `analysis-results/<pk>/review/` | PUT 审核（pending/adopted/ignored/investigating） |

## 4. 前端页面

目录：[frontend/src/pages/System/](file:///d:/code/GAF/frontend/src/pages/System/)

| 页面 | 路由 | 用途 |
|---|---|---|
| `SystemSettings.tsx` | `/system/settings` | 主页 9 Tabs：cleanup/config/diagnostic/debug/language/infra/danger/security/devices |
| `ConfigManagementPage.tsx` | `/system/config` | 配置管理（动态 schema 表单 + Alas-style 迁移 GUI） |
| `Notifications.tsx` | `/system/notifications` | 通知中心 + NotificationPreferences + WebhookConfigPanel |
| `Plugins.tsx` | `/system/plugins` | 插件市场（上传 .gafplugin + 启停 + 沙箱执行） |
| `ApiKeysPage.tsx` | `/system/api-keys` | API Key CRUD（权限 + IP 白名单 + 过期） |
| `FeatureFlagsPage.tsx` | `/system/feature-flags` | 功能开关 CRUD（灰度百分比 + 角色白名单） |
| `AuditLogPage.tsx` | `/system/audit-log` | 审计日志查看器（8 种 action 颜色 + 30+ resource_type i18n） |

> **Backup 页面路由**：`Backup.tsx` 位于 `frontend/src/pages/Ops/`，路由 `/system/backup`（TD-099 fix 3 从 `/ops/backup` 迁移，旧 /ops/backup 链接已迁移为 /system/backup（重定向已移除）），含手动创建/恢复 + 每日 02:30 定时备份（gaf_core.tasks.scheduled_backup，保留 7 份）。

## 5. 审计资源类型

`AuditResourceType` 常量（前后端 i18n 映射已对齐）：
`UNATTENDED_STRATEGY` / `LLM_CONFIG` / `FEATURE_FLAG` / `APP_SETTINGS` / `DEBUG_LOG_ARCHIVE` / `CRASH_REPORT`

## 6. 已知限制

- `agent_debug` 和 `wait_when_background` 不是独立模型，存于 `AppSettings` 表（`category='agent'`）
- 5 层恢复策略 5 层 handler 信号源全部接入 + device_command 协议 (2026-07-29 P-048 完成):
  - L1 `stepLevel`: `tasks/signals.py::ExecutionStep post_save` (既有 P-020-D)
  - L2 `taskLevel`: `tasks/signals.py::TaskExecution post_save` (既有 P-020-D)
  - L3 `appLevel`: `scheduler/tasks.py::detect_app_freeze` Celery beat (60s) → `handle_app_freeze`
  - L4 `deviceLevel`: `agents/signals.py::trigger_device_crash_recovery` (Device status→ERROR) → `handle_device_crash`
  - L5 `systemLevel`: `tasks/heartbeat.py::check_agent_heartbeats` Celery beat (5s) → `handle_agent_timeout`
  - device-command 动作 (`restart_app`/`restart_emulator`/`reconnect_adb`/`relogin`/`notify_only`/`switch_backup`) 通过新增 `device.command` WS 协议消息类型委托 agent 执行, agent 端复用既有 `EmulatorController`/`ADBDevice.reboot`/`WindowsDevice.restart_app` 实现
  - `_execute_warmup_step` 通过 device_command 委托 agent 执行 (start_emulator→restart_emulator, auto_login→relogin 降级)（⚠️ 2026-08-28 实查: engine 仍为占位实现，见 scheduler.md §9.4）
