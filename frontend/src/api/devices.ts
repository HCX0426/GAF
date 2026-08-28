/**
 * device related API
 * includes device CRUD, group management, screenshot operation interfaces
 * Phase 3 additions: scan, register, test screenshot, lock/unlock, stats, compatibility check
 */
import client from './client';
import type {
  Device,
  DeviceGroup,
  DeviceQueryParams,
  ScreenshotResponse,
  PaginatedResponse,
  ScanResponse,
  ScreenshotTestResult,
  LockResponse,
  DeviceStats,
  CompatibilityCheckResult,
  DeviceRegisterParams,
} from '@/types/models';

/** get device list (supports filter) */
export async function fetchDevices(params?: DeviceQueryParams): Promise<PaginatedResponse<Device>> {
  const res = await client.get<PaginatedResponse<Device>>('/devices/', { params });
  return res.data;
}

/** get single device details */
export async function fetchDevice(id: number): Promise<Device> {
  const res = await client.get<Device>(`/devices/${id}/`);
  return res.data;
}

/** register device */
export async function createDevice(data: Partial<Device>): Promise<Device> {
  const res = await client.post<Device>('/devices/', data);
  return res.data;
}

/** update device info */
export async function updateDevice(id: number, data: Partial<Device>): Promise<Device> {
  const res = await client.put<Device>(`/devices/${id}/`, data);
  return res.data;
}

/** partial update device info (PATCH) */
export async function patchDevice(id: number, data: Partial<Device>): Promise<Device> {
  const res = await client.patch<Device>(`/devices/${id}/`, data);
  return res.data;
}

/** remove device */
export async function deleteDevice(id: number): Promise<void> {
  await client.delete(`/devices/${id}/`);
}

/** get device group list */
export async function fetchDeviceGroups(): Promise<PaginatedResponse<DeviceGroup>> {
  const res = await client.get<PaginatedResponse<DeviceGroup>>('/device-groups/');
  return res.data;
}

/** create device group */
export async function createDeviceGroup(data: {
  name: string;
  devices?: number[];
  parent?: number;
}): Promise<DeviceGroup> {
  const res = await client.post<DeviceGroup>('/device-groups/', data);
  return res.data;
}

/** update device group */
export async function updateDeviceGroup(
  id: number,
  data: { name?: string; devices?: number[]; parent?: number },
): Promise<DeviceGroup> {
  const res = await client.put<DeviceGroup>(`/device-groups/${id}/`, data);
  return res.data;
}

/** delete device group */
export async function deleteDeviceGroup(id: number): Promise<void> {
  await client.delete(`/device-groups/${id}/`);
}

/** request device screenshot */
export async function requestScreenshot(deviceId: number): Promise<ScreenshotResponse> {
  const res = await client.post<ScreenshotResponse>(`/devices/${deviceId}/screenshot/`);
  return res.data;
}

/** Phase 3 — scan devices (emulators + windows) */
export async function scanDevices(type: 'android' | 'windows' | 'all' = 'all'): Promise<ScanResponse> {
  const res = await client.get<ScanResponse>('/devices/scan/', { params: { type } });
  return res.data;
}

/** Phase 3 — register device */
export async function registerDevice(data: DeviceRegisterParams): Promise<Device> {
  const res = await client.post<Device>('/devices/register/', data);
  return res.data;
}

/** Health check all devices - returns online/offline status */
export async function healthCheckDevices(): Promise<{
  checked_at: string;
  total: number;
  online: number;
  offline: number;
  results: Array<{
    id: number;
    name: string;
    device_type: string;
    old_status: string;
    new_status: string;
    is_online: boolean;
    reason: string;
  }>;
}> {
  const res = await client.post('/devices/health-check/');
  return res.data;
}

/** Phase 3 — test screenshot */
export async function testScreenshot(deviceId: number, method?: string): Promise<ScreenshotTestResult> {
  const params = method && method !== 'auto' ? { method } : undefined;
  const res = await client.get<ScreenshotTestResult>(`/devices/${deviceId}/test-screenshot/`, { params });
  return res.data;
}

/** Phase 3 — lock device */
export async function lockDevice(deviceId: number, force?: boolean): Promise<LockResponse> {
  const res = await client.post<LockResponse>(
    `/devices/${deviceId}/lock/`,
    {},
    { params: force ? { force: true } : undefined },
  );
  return res.data;
}

/** Phase 3 — unlock device */
export async function unlockDevice(deviceId: number, force?: boolean): Promise<LockResponse> {
  const res = await client.post<LockResponse>(
    `/devices/${deviceId}/unlock/`,
    {},
    { params: force ? { force: true } : undefined },
  );
  return res.data;
}

/** Phase 3 — get device performance stats */
export async function fetchDeviceStats(deviceId: number): Promise<DeviceStats> {
  const res = await client.get<DeviceStats>(`/devices/${deviceId}/stats/`);
  return res.data;
}

/** Phase 3 — check resolution compatibility */
export async function checkCompatibility(deviceId: number, resourcePackId: number): Promise<CompatibilityCheckResult> {
  const res = await client.post<CompatibilityCheckResult>('/devices/check-compatibility/', {
    device_id: deviceId,
    resource_pack_id: resourcePackId,
  });
  return res.data;
}

/** platform capabilities query */
export async function fetchPlatformCapabilities<T = Record<string, unknown>>(): Promise<T> {
  const res = await client.get<T>('/devices/platform-capabilities/');
  return res.data;
}

export interface EmulatorInstance {
  name: string;
  index: number;
  status: string;
  is_running: boolean;
  emulator_type: string;
}

export interface EmulatorListResponse {
  instances: EmulatorInstance[];
  ldconsole_available: boolean;
  error?: string;
}

export interface LifecycleResult {
  success: boolean;
  message: string;
  raw_output?: string;
  instance?: EmulatorInstance;
}

export interface HealthCheckResult {
  instance_name: string;
  instance_index: number;
  is_healthy: boolean;
  adb_connected: boolean;
  screen_fps: number;
  anr_detected: boolean;
  response_time_ms: number;
  details: Record<string, unknown>;
  checked_at: string;
  error: string;
}

/** Emulator lifecycle action response (start/stop/restart/adb/health_check/etc.) */
export interface EmulatorActionResponse {
  success: boolean;
  message: string;
  raw_output?: string;
  health_check?: HealthCheckResult;
  health_checks?: HealthCheckResult[];
}

/** List all emulator instances */
export async function fetchEmulatorInstances(): Promise<EmulatorListResponse> {
  const res = await client.get<EmulatorListResponse>('/devices/emulator-lifecycle/');
  return res.data;
}

/** Execute emulator lifecycle operation (start/stop/restart/create/delete/adb/health_check/auto_restart/health_check_all) */
export async function executeEmulatorAction(
  action: string,
  params: {
    name_or_index?: string;
    instance_name?: string;
    adb_serial?: string;
    command?: string;
    max_retries?: number;
  },
): Promise<EmulatorActionResponse> {
  const res = await client.post('/devices/emulator-lifecycle/', {
    action,
    ...params,
  });
  return res.data;
}

/** Phase R10 — Click device at coordinates */
export interface ClickParams {
  x: number;
  y: number;
  button?: 'left' | 'right' | 'middle';
  method?: string;
  /** Resolution of the screenshot frame the coordinates are relative to. */
  screenshot_width?: number;
  screenshot_height?: number;
}

export interface ClickResult {
  success: boolean;
  method: string;
  error?: string;
}

export async function clickDevice(deviceId: number, params: ClickParams): Promise<ClickResult> {
  const res = await client.post<ClickResult>(`/devices/${deviceId}/click/`, params);
  return res.data;
}

/** Phase R10/R11 — Unified input (key_press/text_input/swipe/scroll) */
export interface InputParams {
  action: 'key_press' | 'text_input' | 'swipe' | 'scroll';
  key?: string;
  text?: string;
  x1?: number;
  y1?: number;
  x2?: number;
  y2?: number;
  duration_ms?: number;
  x?: number;
  y?: number;
  delta?: number;
  method?: string;
  /** Resolution of the screenshot frame the coordinates are relative to. */
  screenshot_width?: number;
  screenshot_height?: number;
}

export interface InputResult {
  success: boolean;
  method: string;
  action: string;
  error?: string;
}

export async function inputDevice(deviceId: number, params: InputParams): Promise<InputResult> {
  const res = await client.post<InputResult>(`/devices/${deviceId}/input/`, params);
  return res.data;
}

/** Template matching - find template image in device screenshot */
export interface TemplateMatchParams {
  template_base64: string;
  threshold?: number;
  scales?: number[];
  method?: string;
}

export interface TemplateMatchResult {
  success: boolean;
  matched: boolean;
  score: number;
  x: number;
  y: number;
  width: number;
  height: number;
  center_x: number;
  center_y: number;
  /** Client-scaled coordinates (DPI-aware). Use these for clicking. */
  center_x_client?: number;
  center_y_client?: number;
  client_scale?: number;
  scale: number;
  error?: string;
}

export async function templateMatchDevice(deviceId: number, params: TemplateMatchParams): Promise<TemplateMatchResult> {
  const res = await client.post<TemplateMatchResult>(`/devices/${deviceId}/template-match/`, params);
  return res.data;
}

/** Color detection - find pixels in HSV range */
export interface ColorDetectParams {
  lower_hsv: [number, number, number];
  upper_hsv: [number, number, number];
  min_pixels?: number;
  region?: [number, number, number, number];
}

export interface ColorDetectResult {
  success: boolean;
  matched: boolean;
  pixel_count: number;
  bbox: [number, number, number, number];
  centroid: [number, number];
  error?: string;
}

export async function colorDetectDevice(deviceId: number, params: ColorDetectParams): Promise<ColorDetectResult> {
  const res = await client.post<ColorDetectResult>(`/devices/${deviceId}/color-detect/`, params);
  return res.data;
}

/** Phase R10-C — App management (launch/force_stop/list/uninstall) */
export interface AppActionParams {
  action: 'launch' | 'force_stop' | 'list' | 'uninstall';
  package?: string;
  filter?: string;
  exe_path?: string;
  pid?: number;
}

export interface AppActionResult {
  success: boolean;
  action: string;
  data?: {
    packages?: string[];
    count?: number;
    processes?: Array<{ name: string; pid: number }>;
    package?: string;
    method?: string;
    output?: string;
    exe_path?: string;
    target?: string | number;
  } | null;
  error?: string;
}

export async function appDevice(deviceId: number, params: AppActionParams): Promise<AppActionResult> {
  const res = await client.post<AppActionResult>(`/devices/${deviceId}/app/`, params);
  return res.data;
}

/** Phase R10-D — Device info query (battery/screen/system) */
export interface DeviceInfoParams {
  query: 'battery' | 'screen' | 'system' | 'all';
}

export interface DeviceInfoResult {
  success: boolean;
  data?: {
    battery_level?: number | null;
    battery_charging?: boolean | null;
    screen_width?: number | null;
    screen_height?: number | null;
    android_version?: string | null;
    model?: string | null;
    os_version?: string | null;
    device_type?: string;
  } | null;
  error?: string;
}

export async function infoDevice(deviceId: number, params: DeviceInfoParams): Promise<DeviceInfoResult> {
  const res = await client.post<DeviceInfoResult>(`/devices/${deviceId}/info/`, params);
  return res.data;
}
