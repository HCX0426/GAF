/**
 * setup wizard API
 */
import apiClient from './client';

/** health check data structure */
export interface HealthResponse {
  db: 'pass' | 'warning' | 'fail';
  db_message: string;
  redis: 'pass' | 'warning' | 'fail';
  redis_message: string;
  celery: 'pass' | 'warning' | 'fail';
  celery_message: string;
  ws: 'pass' | 'warning' | 'fail';
  ws_message: string;
  disk: 'pass' | 'warning' | 'fail';
  disk_message: string;
  memory: 'pass' | 'warning' | 'fail';
  memory_message: string;
}

/** environment check items */
export interface EnvCheckItem {
  current_version: string;
  required_version: string;
  status: 'pass' | 'fail' | 'warning';
  suggestion: string | null;
}

/** environment check response */
export interface EnvCheckResponse {
  python: EnvCheckItem;
  node: EnvCheckItem;
  adb: EnvCheckItem;
  postgresql: EnvCheckItem;
  redis: EnvCheckItem;
  disk: EnvCheckItem;
}

/** sample task pack for setup wizard */
export interface ExamplePack {
  id: number;
  name: string;
  description: string;
  category: string;
  task_count: number;
  icon?: string;
}

/** device scan result item */
export interface DeviceScanResult {
  name: string;
  device_type: string;
  identifier: string;
  status: string;
  adb_serial?: string;
  hwnd?: number;
  emulator?: string;
  resolution?: { width: number; height: number };
}

/** check if admin user already exists */
export function checkHasAdmin(): Promise<boolean> {
  return apiClient.get('/accounts/init/check-admin/').then((res) => res.data.exists);
}

/** create admin account */
export function createAdmin(username: string, password: string): Promise<void> {
  return apiClient.post('/accounts/init/create-admin/', { username, password });
}

/** get system health status */
export function getSystemHealth(): Promise<HealthResponse> {
  return apiClient.get('/accounts/init/health/').then((res) => res.data);
}

/** get sample task pack list */
export function getExamplePacks(): Promise<ExamplePack[]> {
  return apiClient.get('/accounts/init/example-packs/').then((res) => res.data);
}

/** import sample task pack */
export function importExamplePacks(packIds?: number[]): Promise<void> {
  return apiClient.post('/accounts/init/import/', { pack_ids: packIds || [] });
}

/** get environment diagnostics info */
export function getEnvCheck(): Promise<EnvCheckResponse> {
  return apiClient.get('/accounts/init/env-check/').then((res) => res.data);
}

/** scan local devices */
export function scanDevices(): Promise<DeviceScanResult[]> {
  return apiClient.get('/devices/scan/').then((res) => res.data);
}
