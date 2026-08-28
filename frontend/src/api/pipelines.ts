/**
 * Pipeline API client
 * backend field name: graph_data (physical column: pipeline_data, bridged via db_column)
 * backend route: /pipeline/pipelines/ (DRF Router registered in pipeline app)
 */
import apiClient from './client';
import { generateTraceId, setLastTraceId } from '@/utils/traceId';

export interface PipelineSummary {
  id: number;
  name: string;
  description: string;
  version: number;
  is_template: boolean;
  estimated_duration_ms: number | null;
  user: number;
  updated_at: string;
}

export interface PipelineDetail {
  id: number;
  name: string;
  description: string;
  user: number;
  graph_data: Record<string, unknown>;
  version: number;
  is_template: boolean;
  estimated_duration_ms: number | null;
  created_at: string;
  updated_at: string;
}

export interface PipelineSnapshotItem {
  id: number;
  version: number;
  graph_data: Record<string, unknown>;
  change_summary: string;
  created_at: string;
}

export interface ValidateResult {
  check: string;
  status: 'pass' | 'warn' | 'fail';
  message: string;
  node_id?: string;
  suggestion?: string;
}

export function listPipelines(params?: {
  search?: string;
  page?: number;
  page_size?: number;
  is_template?: boolean;
  signal?: AbortSignal;
}): Promise<{ results: PipelineSummary[]; count: number }> {
  const { signal, ...queryParams } = params || {};
  return apiClient.get('/pipeline/pipelines/', { params: queryParams, signal }).then((r) => r.data);
}

export function getPipeline(id: number, options?: { signal?: AbortSignal }): Promise<PipelineDetail> {
  return apiClient.get(`/pipeline/pipelines/${id}/`, { signal: options?.signal }).then((r) => r.data);
}

export function createPipeline(data: Partial<PipelineDetail>): Promise<PipelineDetail> {
  return apiClient.post('/pipeline/pipelines/', data).then((r) => r.data);
}

export function updatePipeline(id: number, data: Partial<PipelineDetail>): Promise<PipelineDetail> {
  return apiClient.put(`/pipeline/pipelines/${id}/`, data).then((r) => r.data);
}

export function patchPipeline(id: number, data: Partial<PipelineDetail>): Promise<PipelineDetail> {
  return apiClient.patch(`/pipeline/pipelines/${id}/`, data).then((r) => r.data);
}

export function deletePipeline(id: number): Promise<void> {
  return apiClient.delete(`/pipeline/pipelines/${id}/`);
}

export function getPipelineSnapshots(id: number): Promise<PipelineSnapshotItem[]> {
  return apiClient.get(`/pipeline/pipelines/${id}/snapshots/`).then((r) => r.data);
}

/** Fetch a single pipeline snapshot by version number */
export function getPipelineSnapshotByVersion(pipelineId: number, version: number): Promise<PipelineSnapshotItem> {
  return apiClient
    .get<PipelineSnapshotItem>(`/pipeline/pipelines/${pipelineId}/snapshots/${version}/`)
    .then((r) => r.data);
}

/** Restore a pipeline to a specific snapshot version. */
export function restorePipeline(id: number, version: number): Promise<PipelineDetail> {
  return apiClient.post(`/pipeline/pipelines/${id}/restore/${version}/`).then((r) => r.data);
}

// Task 4.38 (P0-10, 2026-07-28): validate API 契约对齐
// 之前声明返回 `{ valid, errors }` 但后端 `PipelineValidateView.post` 返回 `{ results: CheckItem[] }`,
// 导致前端 res.valid 永远 undefined, validate 按钮始终显示"0 个错误"。
// 现在直接消费后端 results (CheckItem[]), 由调用方按 status === 'fail' 过滤。
export function validatePipeline(graph_data: Record<string, unknown>): Promise<{ results: ValidateResult[] }> {
  return apiClient.post('/pipeline/pipelines/validate/', { graph_data }).then((r) => r.data);
}

export interface ExecuteResult {
  pipeline_id: string;
  pipeline_name: string;
  agent_id: string;
  status: string;
  message: string;
}

export function executePipeline(id: number, device_id?: string): Promise<ExecuteResult> {
  // C1 (spec 2026-07-30): 生成 trace_id 存 sessionStorage, request 拦截器自动加
  // X-Trace-Id header, 后端 views.execute 从 header 取 trace_id 贯穿 WS 帧/日志。
  setLastTraceId(generateTraceId());
  return apiClient.post(`/pipeline/pipelines/${id}/execute/`, { device_id }).then((r) => r.data);
}
