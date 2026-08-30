/**
 * Frontend WebSocket event type constants.
 *
 * Single source of truth for event names subscribed via wsClient.onMessage /
 * useWebSocket. Backend broadcasts these types via channels group_send;
 * backend constants are defined in `backend/protocol/constants.py`
 * `FrontendEventType` class (TD-201/202 修复 2026-07-18 — backend consolidation).
 *
 * Pattern A (wsClient.onMessage / useWebSocket): use these constants.
 * Pattern B (internal message.type comparison in useNotificationWebSocket /
 * useLogStream): also use these constants.
 *
 * Distinct from Worker ↔ Backend protocol types (MessageType in
 * backend/protocol/constants.py) which cover the Worker WebSocket frame types.
 */

export const WS_EVENT = {
  /** Worker heartbeat broadcast (backend FrontendEventType.AGENT_HEARTBEAT) */
  AGENT_HEARTBEAT: 'agent_heartbeat',
  /** Worker status change broadcast */
  AGENT_STATUS: 'agent_status',
  /** Task execution log stream (unified; replaces legacy 'task_log') */
  EXECUTION_LOG: 'execution_log',
  /** Execution step status update */
  EXECUTION_STEP_UPDATE: 'execution_step_update',
  /** Screenshot frame stream (device live view) */
  SCREENSHOT_FRAME: 'screenshot_frame',
  /** Notification push (used by useNotificationWebSocket Pattern B) */
  NOTIFICATION: 'notification',
  /** Worker log entry stream (used by useLogStream Pattern B) */
  LOG_ENTRY: 'log.entry',
  /** Device status broadcast (TD-201 修复 2026-07-18: renamed device_status → device.status for naming consistency) */
  DEVICE_STATUS: 'device.status',
  /** Device record updated (DB-side change broadcast) */
  DEVICE_UPDATED: 'device.updated',
  /** Device metrics refreshed (CPU/memory/uptime) */
  DEVICE_METRICS_UPDATED: 'device.metrics_updated',
  /** Device registered (new device discovered via agent.device.sync) */
  DEVICE_REGISTERED: 'device.registered',
  /** Device capabilities updated (agent reports new capability set) */
  DEVICE_CAPABILITIES_UPDATED: 'device.capabilities_updated',
} as const;

export type WsEvent = (typeof WS_EVENT)[keyof typeof WS_EVENT];
