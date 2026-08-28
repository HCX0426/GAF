/**
 * GAF app centralized config
 * has version number,API before suffix, app name etc. unified from this file read fetch, avoid hardcode
 */

/** app name */
export const APP_NAME = 'GAF';

/** app version number */
export const APP_VERSION = '2.0.0';

/** API version before suffix — 从构建时环境变量读取，与 backend/app_info.py 同步 */
export const API_PREFIX = import.meta.env.VITE_API_PREFIX || '/api/v2';

/** API request timeout ( milliseconds ) */
export const API_TIMEOUT = 30000;

/** WebSocket base path (dashboard channel per api-contract §9.1) */
export const WS_PATH = '/ws/dashboard/';

/** WebSocket base path for device-level ADB log stream (TD-366, synced with backend GAF_WS_DEVICES_PATH) */
export const WS_DEVICES_PATH = import.meta.env.VITE_WS_DEVICES_PATH || '/ws/devices/';

/** default paginate size */
export const DEFAULT_PAGE_SIZE = 20;

/** most large paginate size */
export const MAX_PAGE_SIZE = 100;

/** L5: Token refresh threshold (seconds before expiry to proactively refresh) */
export const TOKEN_REFRESH_THRESHOLD_SECONDS = 60;

/** L10: WebSocket heartbeat interval (milliseconds) */
export const WS_HEARTBEAT_INTERVAL = 30000;

/** L10: WebSocket pong timeout (milliseconds) — disconnect after 2 missed pongs */
export const WS_PONG_TIMEOUT = 15000;

/**
 * build after end API URL tool function
 * auto spec transform path, ensure single slash trailing, avoid Django 301 redirect and double slash issue
 * @param path - API path, like '/tasks','/tasks/' or 'tasks'
 * @returns complete API URL
 */
export function apiUrl(path: string): string {
  const trimmed = path.replace(/^\/+|\/+$/g, '');
  if (!trimmed) return `${API_PREFIX}/`;
  // L8: split path and query — Django APPEND_SLASH expects trailing slash
  // on the path part (before '?'), otherwise it 301-redirects adding an
  // extra HTTP round-trip.
  const queryIdx = trimmed.indexOf('?');
  if (queryIdx === -1) {
    return `${API_PREFIX}/${trimmed}/`;
  }
  const pathPart = trimmed.slice(0, queryIdx);
  const queryPart = trimmed.slice(queryIdx + 1);
  if (!pathPart) {
    return `${API_PREFIX}/?${queryPart}`;
  }
  return `${API_PREFIX}/${pathPart}/?${queryPart}`;
}
