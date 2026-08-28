/**
 * device domain models (s37 split from models.ts — TD-365).
 */

import type { API } from '@/types/api';
export type AIMessageRole = 'user' | 'assistant' | 'system';

/** AI message */

export interface AIMessage {
  id: string;
  role: AIMessageRole;
  content: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

/** game account login method */

export type LoginMethod = 'password' | 'qr_scan' | 'token' | 'steam';

/**
 * Game account — schema reference (spec-29j Phase 2c, 2026-07-19).
 *
 * Migrated from hand-written interface to `API.components['schemas']['GameAccount']`
 * after TD-266 Phase 3a added `resource_pack_detail` (nested ResourcePack
 * summary) so the frontend can render the bound pack name without a second
 * round-trip.
 *
 * Schema differences vs the pre-migration hand-written interface:
 *   - `resource_pack`: schema `number | null` (FK id, write-capable) vs
 *     models was `{ id; name; version } | null` (nested object). **Breaking**
 *     for consumers that read `account.resource_pack?.id` / `.name` — they
 *     must use `account.resource_pack` directly as the id, or read
 *     `account.resource_pack_detail?.name` for display. The pre-migration
 *     cast in `GameAccountEditor.tsx` (`(account as Record<string, unknown>)
 *     .resource_pack?.id`) was already broken under the old type and remains
 *     broken under the new type — to be fixed in a follow-up that switches
 *     the form to use `account.resource_pack` as the id directly.
 *   - `resource_pack_detail`: schema `components['schemas']['ResourcePack']`
 *     (nested object, spec-29f Phase 3a addition) — new field, not in
 *     pre-migration models.
 *   - `game_profile`: schema `number | null` — new field (not in
 *     pre-migration models).
 *   - `password`: schema absent (write_only) vs models had `password?: string`.
 *     Consumers should never read `account.password` — use the create/update
 *     request types for write paths.
 *   - `status`: schema `string` (not constrained to enum) vs models was
 *     `'ok' | 'warn' | 'error' | 'unknown'`. Consumers that exhaustively
 *     switch on status values still work because unknown values fall through
 *     to default branches.
 *   - `login_method`: schema `LoginMethodEnum` vs models `LoginMethod`.
 *     Same string literal union — equivalent.
 *   - `owner` / `login_count` / `execution_count` / `created_at` /
 *     `updated_at`: schema `readonly` vs models mutable. Consumers should
 *     not mutate these fields anyway.
 *   - `server_region` / `login_method` / `group` / `is_active`: schema
 *     optional vs models required. Consumers should use optional chaining
 *     when reading.
 *   - `group_name`: schema `string` (always defined) vs models
 *     `string | null`. Empty string in schema replaces null — falsy check
 *     `name ? ... : ...` still works.
 */

export type GameAccount = API.components['schemas']['GameAccount'];

/** game account create request */

export interface GameAccountCreateRequest {
  game_name: string;
  username: string;
  password: string;
  server_region: string;
  login_method: string;
  group?: number | null;
}

/** game account update request */

export interface GameAccountUpdateRequest {
  game_name?: string;
  username?: string;
  password?: string;
  server_region?: string;
  login_method?: string;
  group?: number | null;
  is_active?: boolean;
}

/** device type */

export type DeviceType = 'windows' | 'emulator';

/** device control mode — matches backend Device.ControlMode choices.
 * v3 §2.8.1: 'auto' = inherit from GameProfile defaults at runtime. */

export type ControlMode = 'auto' | 'foreground' | 'background' | 'pseudo_background';

/** v3 §2.8.1: resolved methods after GameProfile inheritance.
 * Returned by DeviceSerializer.resolved_methods (read-only).
 *
 * P-011 Spec A: includes multi_game_restricted + original_* keys for
 * frontend mode-selector binding. */

export interface ResolvedDeviceMethods {
  screenshot_method: string;
  input_method: string;
  control_mode: string;
  multi_game_restricted?: boolean;
  original_screenshot_method?: string;
  original_input_method?: string;
}

/** run row platform */

export type RuntimePlatform = 'windows' | 'macos' | 'linux';

/** device status type — matches backend Device.Status choices */

export type DeviceStatus = 'online' | 'offline' | 'busy' | 'error' | 'locked';

/** resolution */

export interface Resolution {
  width: number;
  height: number;
}

/** associate Agent summary — matches backend DeviceSerializer.get_agent_info() */

export interface AgentInfo {
  id: number;
  agent_id: string;
  hostname: string;
  ip_address: string;
  status: string;
  last_heartbeat: string | null;
}

/**
 * Device info — schema reference (spec-29j Phase 2d, 2026-07-19).
 *
 * Migrated from hand-written interface to `API.components['schemas']['Device']`
 * after spec-29k (TD-259 #7 Phase 2d) added `DeviceStatsSchema` to
 * `agents/schema_types.py` and converted `DeviceSerializer.device_stats`
 * from `DictField` to `SerializerMethodField` + `@extend_schema_field(DeviceStatsSchema)`,
 * giving the 10 known stats keys precise types.
 *
 * Schema differences vs the pre-migration hand-written interface:
 *   - `device_stats`: schema `DeviceStatsSchema` (10 typed fields, all
 *     optional / nullable) vs models `DeviceStats` (11 required fields
 *     including `resolution: Resolution` and `input_method`).
 *     - Schema is more accurate: `DeviceStats` was aspirational — the
 *       backend only writes 4-10 fields incrementally, never all 11.
 *     - `resolution` and `input_method` are not in schema (they are
 *       top-level Device fields, not stats fields).
 *     - Consumers access `device.device_stats?.screenshot_latency_avg_ms`
 *       (still works — schema type is `number | null`, was `number | null`).
 *   - `agent_info` / `resolution` / `resolved_methods`: schema typed via
 *     `AgentInfoSchema` / `ResolutionSchema` / `ResolvedDeviceMethodsSchema`
 *     (spec-29f Phase 1) vs models hand-written. Equivalent shape.
 *   - `status`: schema `DeviceStatusEnum` (`'online' | 'offline' | 'busy'
 *     | 'error'`) vs models `DeviceStatus` (same 4 + `'locked'`). The
 *     `'locked'` state is a frontend-only concept derived from
 *     `locked_by_username != null` — the backend never sets
 *     `Device.status = 'locked'`. Consumers that did
 *     `device.status === 'locked'` should switch to
 *     `device.locked_by_username != null` (most already do).
 *   - `multi_game_restricted` / `allowed_screenshot_methods` /
 *     `allowed_input_methods`: schema typed (spec-29f Phase 1) vs models
 *     hand-written. Equivalent shape.
 *   - `device_type`: schema `DeviceDeviceTypeEnum` vs models `DeviceType`.
 *     Same string literal union — equivalent.
 *   - `control_mode`: schema `ControlModeEnum` vs models `ControlMode`.
 *     Same string literal union — equivalent.
 *   - Many fields: schema optional vs models required (`name` /
 *     `screenshot_fps` / `extra_info` / `adb_serial` / `window_handle` /
 *     `created_at` / `updated_at`). Consumers should use optional chaining.
 *   - `locked_by_username`: schema `string` (always defined) vs models
 *     `string | null`. Empty string in schema replaces null — falsy
 *     checks (`locked_by_username ? ... : ...`) still work.
 */

export type Device = API.components['schemas']['Device'];

/** device group */

export interface DeviceGroup {
  id: number;
  name: string;
  user: number;
  parent: number | null;
  children: DeviceGroupTree[];
  devices: number[];
  device_count: number;
  devices_detail: Device[];
  created_at: string;
  updated_at: string;
}

/** device group tree node */

export interface DeviceGroupTree {
  id: number;
  name: string;
  children: DeviceGroupTree[];
}

/** device discovery response */

export interface DiscoverResponse {
  devices: Device[];
}

/** device scan response */

export interface ScanResponse {
  android: ScanEmulatorItem[];
  windows: ScanWindowItem[];
  scan_error?: string;
}

/** scan result - emulator */

export interface ScanEmulatorItem {
  name: string;
  emulator: string;
  adb_port: number;
  adb_serial: string;
  status: string;
  resolution?: Resolution;
  android_version: string;
}

/** scan result - window */

export interface ScanWindowItem {
  title: string;
  process_name: string;
  hwnd: string;
  resolution: Resolution;
  is_game: boolean;
}

/** test screenshot response */

export interface ScreenshotTestResult {
  screenshot_base64: string | null;
  latency_ms: number;
  fps: number;
  resolution: Resolution;
  screenshot_method: string;
  available_methods?: string[];
  success: boolean;
  error: string | null;
}

/** device lock / unlock response */

export interface LockResponse {
  status: 'locked' | 'unlocked';
  locked_by?: string;
  locked_at?: string;
  message?: string;
  error?: string;
}

/** device performance stats */

export interface DeviceStats {
  fps_avg: number | null;
  fps_min: number | null;
  fps_max: number | null;
  screenshot_latency_avg_ms: number | null;
  input_latency_avg_ms: number | null;
  uptime_seconds: number | null;
  total_screenshots: number;
  screenshot_method: string;
  input_method: string;
  resolution: Resolution;
  dpi: number | null;
}

/** resolution compatible check result */

export interface CompatibilityCheckResult {
  is_compatible: boolean;
  device_resolution: Resolution;
  pack_resolution: Resolution;
  width_ratio: number;
  height_ratio: number;
  scale_suggestion: number;
  message: string;
}

/** device register param */

export interface DeviceRegisterParams {
  name: string;
  agent_type: 'android' | 'windows';
  adb_serial?: string;
  hwnd?: string;
  window_title?: string;
  emulator?: string;
  resolution?: Resolution;
  resolution_width?: number;
  resolution_height?: number;
}

/** device query params */

export interface DeviceQueryParams {
  device_type?: DeviceType;
  status?: DeviceStatus;
  agent?: number;
  search?: string;
  page?: number;
  page_size?: number;
}

/** Pipeline node type — 37 kinds, reference MaaFramework Pipeline JSON
 *
 * Coverage: 21 base types + 16 extended types (composite match, advanced
 * input, Maa protocol, neural network, sort_select). Mirrors the agent-side
 * node registry in agent/src/engine/nodes/__init__.py so the frontend editor
 * can offer the same node set the backend parser accepts.
 */
