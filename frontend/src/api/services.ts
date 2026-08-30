/**
 * Service management API — 服务状态列表 + 服务终端日志 (spec 2026-08-29-services-management-monitor).
 * 数据源: daemon 健康快照 + 服务日志文件, 供系统页签"服务管理"页使用.
 */
import client from './client';

/** 单个服务状态 (健康 + 进程 + 报错信息) */
export interface ServiceInfo {
  name: string;
  healthy: boolean | null;
  detail: string | null;
  ts: number | null;
  running: boolean | null;
  pid: number | null;
  port: number | null;
  restart_count: number | null;
  error_count: number | null;
  latest_error: string | null;
  log_files: string[];
}

/** GET /monitors/services/ 响应 */
export interface SystemServicesResponse {
  updatedAt: string | null;
  daemon: { running: boolean; pid: number | null };
  services: ServiceInfo[];
}

/** GET /monitors/services/logs/ 响应 */
export interface ServiceLogsResponse {
  service: string;
  path: string | null;
  files: string[];
  lines: string[];
}

/** GET /monitors/services/ — 服务状态列表. */
export async function fetchSystemServices(): Promise<SystemServicesResponse> {
  const res = await client.get<SystemServicesResponse>('/monitors/services/');
  return res.data;
}

/** GET /monitors/services/logs/ — 服务终端日志尾部 (filter=all|error). */
export async function fetchServiceLogs(params: {
  service: string;
  lines?: number;
  filter?: 'all' | 'error';
}): Promise<ServiceLogsResponse> {
  const res = await client.get<ServiceLogsResponse>('/monitors/services/logs/', { params });
  return res.data;
}

/** POST /monitors/services/restart/ — 重启单个服务或全部服务 (daemon 异步执行). */
export async function restartService(service: string): Promise<{ detail?: string; service?: string }> {
  const res = await client.post<{ detail?: string; service?: string }>(
    '/monitors/services/restart/',
    { service },
  );
  return res.data;
}