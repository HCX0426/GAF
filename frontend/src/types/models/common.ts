/**
 * common domain models (s37 split from models.ts — TD-365).
 */

import type { API } from '@/types/api';
export interface PaginationParams {
  page: number;
  page_size: number;
}

/** common paginate response */

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** common API response */

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

/** dashboard stats data */

export interface DashboardStats {
  online_agents: number;
  running_tasks: number;
  today_executions: number;
  success_rate: number;
}

/** WebSocket message type */

export interface WsMessage {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

/** device screenshot response — matches backend DeviceScreenshotView response */

export interface ScreenshotResponse {
  screenshot_base64: string | null;
  latency_ms: number;
  width: number;
  height: number;
  screenshot_method?: string;
  error?: string | null;
}

/** device operation command */

export interface DeviceCommand {
  agent_id: string;
  command: string;
  params: Record<string, unknown>;
}

/**
 * Game profile configuration — schema reference (spec-29j Phase 2c, 2026-07-19).
 *
 * Migrated from hand-written interface to `API.components['schemas']['GameProfile']`
 * after TD-266 Phase 3b fixed the 3 JSONField schema regressions.
 *
 * Schema differences vs the pre-migration hand-written interface:
 *   - `ui_reference_resolution`: schema `{ [key: string]: number }` (DictField)
 *     vs models was `{ w: number; h: number }`. Consumers that accessed
 *     `.w` / `.h` directly need a runtime cast: `(profile.ui_reference_resolution
 *     as { w: number; h: number })`.
 *   - `default_routine_name`: models had it, schema does not (frontend
 *     computed it from a separate lookup). Removed — consumers should use
 *     `default_routine` (FK id) and resolve the name via a separate query
 *     if needed.
 *   - Many fields: schema optional vs models required (`game_name` /
 *     `ocr_language` / `ui_reference_resolution` / `known_popups` /
 *     `resolution_strategy` / `created_at` / `updated_at`).
 *   - `default_control_mode`: schema `DefaultControlModeEnum | BlankEnum`
 *     vs models `string`. The schema enum is more precise.
 */

export type GameProfile = API.components['schemas']['GameProfile'];

/** template annotation — matches backend TemplateAnnotationSerializer (R37-P1) */

export interface TemplateAnnotation {
  id: number;
  template: number;
  annotation_type: string;
  /** Backend JSONField — accepts either a number[] (rect: [x, y, w, h]) or
   *  an arbitrary object (polygon vertices, etc.). */
  points: number[] | Record<string, unknown>;
  label?: string;
  created_at: string;
}

/** LLM config */
