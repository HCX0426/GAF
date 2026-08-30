/**
 * Task-related API
 * Covers task CRUD, execution, cancellation, binding, bulk operations, folder management
 */
import client from './client';
import { generateTraceId, setLastTraceId } from '@/utils/traceId';
import type {
  Task,
  TaskExecution,
  ExecutionStep,
  PaginatedResponse,
  PaginationParams,
  AccountBindingInfo,
  BulkActionResult,
  TaskFolder,
  TaskDeviceMapping,
} from '@/types/models';

/** Fetch task list */
export async function fetchTasks(
  params?: Partial<PaginationParams> & { signal?: AbortSignal },
): Promise<PaginatedResponse<Task>> {
  const { signal, ...queryParams } = params || {};
  const res = await client.get<PaginatedResponse<Task>>('/tasks/', { params: queryParams, signal });
  return res.data;
}

/** Fetch single task detail */
export async function fetchTask(taskId: number): Promise<Task> {
  const res = await client.get<Task>(`/tasks/${taskId}/`);
  return res.data;
}

/** Create new task */
export async function createTask(data: Partial<Task>): Promise<Task> {
  const res = await client.post<Task>('/tasks/', data);
  return res.data;
}

/** Update task */
export async function updateTask(taskId: number, data: Partial<Task>): Promise<Task> {
  const res = await client.put<Task>(`/tasks/${taskId}/`, data);
  return res.data;
}

/** Delete task */
export async function deleteTask(taskId: number): Promise<void> {
  await client.delete(`/tasks/${taskId}/`);
}

/** Execute task */
export async function executeTask(taskId: number, params?: Record<string, unknown>): Promise<TaskExecution> {
  // C1 (spec 2026-07-30): 生成 trace_id 存 sessionStorage, request 拦截器自动加
  // X-Trace-Id header, 后端 dispatch_task 从 header 取 trace_id 贯穿 WS 帧/日志。
  setLastTraceId(generateTraceId());
  const res = await client.post<TaskExecution>(`/tasks/${taskId}/execute/`, { parameters: params });
  return res.data;
}

/** Cancel task execution */
export async function cancelTask(taskId: number): Promise<void> {
  await client.post(`/tasks/${taskId}/cancel/`);
}

/** Cancel task execution (by execution ID) */
export async function cancelExecution(executionId: number): Promise<void> {
  await client.post(`/tasks/task-executions/${executionId}/cancel/`);
}

/** Fetch single execution detail */
export async function fetchExecution(executionId: number): Promise<TaskExecution> {
  const res = await client.get<TaskExecution>(`/tasks/task-executions/${executionId}/`);
  return res.data;
}

/** Fetch task execution history */
export async function fetchExecutions(
  params?: Partial<PaginationParams> & {
    task?: number;
    status?: string;
    ordering?: string;
  },
): Promise<PaginatedResponse<TaskExecution>> {
  const res = await client.get<PaginatedResponse<TaskExecution>>('/tasks/task-executions/', { params });
  return res.data;
}

/** Fetch execution step list */
export async function fetchExecutionSteps(executionId: number): Promise<ExecutionStep[]> {
  const res = await client.get<ExecutionStep[]>(`/tasks/task-executions/${executionId}/steps/`);
  return res.data;
}

/** Fetch device binding list */
export async function fetchDeviceBindings(taskId: number): Promise<Array<TaskDeviceMapping>> {
  const res = await client.get<Array<TaskDeviceMapping>>(`/tasks/bind-devices/${taskId}/`);
  return res.data;
}

/** Batch bind devices */
export async function bindDevices(
  taskId: number,
  mappings: Array<{ device_id: number; is_default?: boolean }>,
): Promise<Array<TaskDeviceMapping>> {
  const res = await client.post<Array<TaskDeviceMapping>>(`/tasks/bind-devices/${taskId}/`, { mappings });
  return res.data;
}

/** Delete single device binding */
export async function deleteDeviceBinding(taskId: number, mappingId: number): Promise<void> {
  await client.delete(`/tasks/bind-devices/${taskId}/${mappingId}/`);
}

/** Fetch account bindings */
export async function fetchAccountBindings(taskId: number): Promise<AccountBindingInfo> {
  const res = await client.get<AccountBindingInfo>(`/tasks/bind-accounts/${taskId}/`);
  return res.data;
}

/** Bind accounts */
export async function bindAccounts(
  taskId: number,
  data: { account_ids: number[]; rotation_rule_id?: number },
): Promise<void> {
  await client.post(`/tasks/bind-accounts/${taskId}/`, data);
}

/** Update parallel config */
export async function updateParallelConfig(
  taskId: number,
  data: { parallel_mode: boolean; max_concurrency: number },
): Promise<void> {
  await client.put(`/tasks/parallel-config/${taskId}/`, data);
}

/** Bulk action */
export async function bulkAction(data: {
  action: 'enable' | 'disable' | 'delete' | 'export';
  task_ids: number[];
}): Promise<BulkActionResult> {
  const res = await client.post<BulkActionResult>('/tasks/bulk-action/', data);
  return res.data;
}

/** Fetch folder list */
export async function fetchTaskFolders(): Promise<PaginatedResponse<TaskFolder>> {
  const res = await client.get<PaginatedResponse<TaskFolder>>('/tasks/folders/');
  return res.data;
}

/** Create folder */
export async function createTaskFolder(data: { name: string; parent?: number }): Promise<TaskFolder> {
  const res = await client.post<TaskFolder>('/tasks/folders/', data);
  return res.data;
}

/** Update folder */
export async function updateTaskFolder(id: number, data: { name?: string; slug?: string }): Promise<TaskFolder> {
  const res = await client.put<TaskFolder>(`/tasks/folders/${id}/`, data);
  return res.data;
}

/** Delete folder */
export async function deleteTaskFolder(id: number): Promise<void> {
  await client.delete(`/tasks/folders/${id}/`);
}

/** Clone task */
export async function cloneTask(taskId: number): Promise<{ id: number; name: string; message: string }> {
  const res = await client.post<{ id: number; name: string; message: string }>(`/tasks/clone/${taskId}/`);
  return res.data;
}

/** Compare two execution results */
export async function compareExecutions(executionId: number, otherId: number): Promise<Record<string, unknown>> {
  const res = await client.post(`/tasks/task-executions/${executionId}/compare/`, { other_id: otherId });
  return res.data;
}

// Feature Flag management
// R37-P3 Stage 7 Task 20a: backend FeatureFlag moved from tasks to settings
// app (TD-039). Endpoint base changed from /tasks/feature-flags/ to
// /settings/feature-flags/. db_table unchanged — zero data migration.

/** Fetch feature flags list */
export async function fetchFeatureFlags(params?: Record<string, unknown>) {
  const res = await client.get('/settings/feature-flags/', { params });
  return res.data;
}

/** Create a new feature flag */
export async function createFeatureFlag(data: Record<string, unknown>) {
  const res = await client.post('/settings/feature-flags/', data);
  return res.data;
}

/** Update feature flag */
export async function updateFeatureFlag(id: number, data: Record<string, unknown>) {
  const res = await client.put(`/settings/feature-flags/${id}/`, data);
  return res.data;
}

/** Delete feature flag */
export async function deleteFeatureFlag(id: number): Promise<void> {
  await client.delete(`/settings/feature-flags/${id}/`);
}

// Audit Log (R37-P3 Stage 7 Task 20a: backend AuditLog moved from tasks to
// accounts app — TD-039. fetchAuditLogs now lives in @/api/accounts.

// TaskChain management (DAG task chain orchestration)
// R37-P3 Stage 7 Task 20a: backend TaskChain moved from tasks to pipeline
// app (TD-039). Endpoint base changed from /tasks/task-chains/ to
// /pipeline/task-chains/. db_table unchanged — zero data migration.

import type { TaskChain } from '@/types/models';

/** Fetch task chain list */
export async function fetchTaskChains(
  params?: Record<string, unknown> & { signal?: AbortSignal },
): Promise<PaginatedResponse<TaskChain>> {
  const { signal, ...queryParams } = params || {};
  const res = await client.get<PaginatedResponse<TaskChain>>('/pipeline/task-chains/', { params: queryParams, signal });
  return res.data;
}

/** Fetch single task chain detail */
export async function fetchTaskChain(chainId: number): Promise<TaskChain> {
  const res = await client.get<TaskChain>(`/pipeline/task-chains/${chainId}/`);
  return res.data;
}

/** Create new task chain */
export async function createTaskChain(data: {
  name: string;
  description?: string;
  dag_data?: Record<string, unknown>;
  is_enabled?: boolean;
}): Promise<TaskChain> {
  const res = await client.post<TaskChain>('/pipeline/task-chains/', data);
  return res.data;
}

/** Update task chain */
export async function updateTaskChain(chainId: number, data: Partial<TaskChain>): Promise<TaskChain> {
  const res = await client.put<TaskChain>(`/pipeline/task-chains/${chainId}/`, data);
  return res.data;
}

/** Delete task chain */
export async function deleteTaskChain(chainId: number): Promise<void> {
  await client.delete(`/pipeline/task-chains/${chainId}/`);
}

// TaskChainNode management (TD-110: nodes can reference Task OR Pipeline).
// Endpoint: /pipeline/chain-nodes/ (DRF APIView, not a ViewSet — uses
// query params + body fields, not REST sub-resource paths).
//
// Note: @/api/misc.ts also exposes untyped chain-node helpers keyed by
// task_id for the legacy TaskDependencyGraph component (task-to-task
// dependency edges). The helpers here are chain-scoped and typed — use
// these for TaskChain DAG composition.

import type { TaskChainNode, ChainNodeType } from '@/types/models';

/** Fetch chain nodes for a TaskChain (optionally filtered by node_type). */
export async function fetchChainNodes(chainId: number, nodeType?: ChainNodeType): Promise<TaskChainNode[]> {
  const params: Record<string, unknown> = { chain_id: chainId };
  if (nodeType) params.node_type = nodeType;
  const res = await client.get<TaskChainNode[]>('/pipeline/chain-nodes/', { params });
  return res.data;
}

/** Create a chain node — caller must set task or pipeline FK based on node_type. */
export async function createChainNode(payload: {
  chain: number;
  node_type: ChainNodeType;
  task?: number | null;
  pipeline?: number | null;
  parent?: number | null;
  condition?: Record<string, unknown>;
  order?: number | null;
}): Promise<TaskChainNode> {
  const res = await client.post<TaskChainNode>('/pipeline/chain-nodes/', payload);
  return res.data;
}

/** Delete a chain node by id. */
export async function deleteChainNode(nodeId: number): Promise<void> {
  await client.delete(`/pipeline/chain-nodes/${nodeId}/`);
}

// Dashboard

/** Daily report overview section returned by /executions/daily-report/ (no date param) */
export interface DashboardDailyOverview {
  total_executions?: number;
  success_rate?: number;
  success_count?: number;
  failed_count?: number;
  [key: string]: unknown;
}

/** Daily report response shape consumed by the Dashboard page */
export interface DashboardDailyReport {
  overview?: DashboardDailyOverview;
  [key: string]: unknown;
}

/**
 * Fetch today's daily execution report for the Dashboard.
 * Endpoint: GET /executions/daily-report/ (no date param — backend defaults to today)
 * Note: lives on the executions domain but executions.ts is read-only in this
 * refactor scope, so the helper is exposed here for the Dashboard page.
 */
export async function getDashboardDailyReport(): Promise<DashboardDailyReport> {
  const res = await client.get<DashboardDailyReport>('/executions/daily-report/');
  return res.data;
}

// N192 B3/B5 P1: Backend validate endpoint types + helper.
// Backend: backend/tasks/views.py TaskViewSet.validate (POST /tasks/{id}/validate/).
// Returns {valid, detail, errors: CheckItem[]} where CheckItem carries node_id +
// suggestion so the frontend can localize errors to specific nodes (N192 B3 P1)
// and show fix suggestions (N192 B6 P1).

/** N192 B3/B5 P1: Backend validation result item — maps to PipelineValidator.CheckItem. */
export interface CheckItem {
  check: string;
  status: 'pass' | 'fail' | 'warn';
  message: string;
  /** 节点 id, 用于前端定位到具体节点高亮 (N192 B3 P1). null = 结构级错误, 非节点级. */
  node_id: string | null;
  /** 修复建议, 前端展示在错误条目下方 (N192 B6 P1). */
  suggestion: string;
}

/** N192 B5 P1: Backend validate endpoint response. */
export interface ValidateResult {
  valid: boolean;
  detail: string;
  /** 后端已过滤掉 pass, 只返回 fail + warn; 前端原样展示. */
  errors: CheckItem[];
}

/**
 * N192 B5 P1: 调用后端 validate 端点校验 task_definition, 在 createTask 之后、
 * navigate 之前调用。返回 CheckItem 列表 (含 node_id/suggestion) 用于节点级错误展示。
 *
 * Endpoint: POST /tasks/{taskId}/validate/ (baseURL 处理 /api/v2 前缀,
 * 与现有 createTask/deleteTask 等保持一致, 不在路径里写 /api/v2)。
 */
export async function validateTask(taskId: number): Promise<ValidateResult> {
  const res = await client.post<ValidateResult>(`/tasks/${taskId}/validate/`);
  return res.data;
}

// Task 1.4 (P1-6): validate-payload 端点 — 校验 inline task_definition, 无需 pk, 不写库。
// 用于前端 Editor 在 createTask 之前预校验, 统一校验口径, 避免 createTask 后 validate
// 失败再 deleteTask 的 race condition (N192 B5 P1)。

/** Task 1.4 (P1-6): validate-payload 端点响应。
 *
 * 与 ValidateResult 的区别: errors 只含 fail 项, warnings 只含 warn 项
 * (ValidateResult.errors 同时含 fail + warn)。这样前端可以分别展示错误和警告。 */
export interface ValidatePayloadResult {
  valid: boolean;
  detail: string;
  /** fail 项的 CheckItem 列表 (阻断性错误, 必须修复才能保存)。 */
  errors: CheckItem[];
  /** warn 项的 CheckItem 列表 (非阻断性警告, 允许保存但建议修复)。 */
  warnings: CheckItem[];
}

/**
 * Task 1.4 (P1-6): 调用 validate-payload 端点预校验 inline task_definition, 不写库。
 *
 * 在 createTask 之前调用, 统一前后端校验口径 (handleValidate + handleSave 都走同一端点),
 * 避免 createTask 后 validate 失败再 deleteTask 的 race condition。
 *
 * Endpoint: POST /tasks/validate-payload/ (baseURL 处理 /api/v2 前缀)。
 */
export async function validatePayload(
  taskDefinition: Record<string, unknown>,
  executionMode: string = 'pipeline',
): Promise<ValidatePayloadResult> {
  const res = await client.post<ValidatePayloadResult>('/tasks/validate-payload/', {
    task_definition: taskDefinition,
    execution_mode: executionMode,
  });
  return res.data;
}

// ─────────────────────────────────────────────
// Node trace (Task 2.4 — N192 B7 P1-7 节点详情抽屉)
// ─────────────────────────────────────────────

/**
 * Task 2.4 (N192 B7 P1-7): 节点 JSONL trace 数据, 来自 agent structured_logger.
 *
 * backend 读取 execution_snapshot.structured_log_path 指向的 JSONL 文件,
 * 按 step_index 过滤 node.execute.start + node.execute.complete 事件后返回.
 * 让用户在 UI 上能看到节点的完整诊断上下文 (config / 前驱 result_data /
 * 当前 result_data / error_msg / error_code), 不必找开发查日志.
 */
export interface NodeTraceData {
  step_index: number;
  node_id: string;
  node_type: string;
  structured_log_available: boolean;
  structured_log_path: string;
  /** start 事件: 节点 input_config, 让用户看到 "这个节点当时配的 threshold/ROI". */
  input_config: Record<string, unknown> | null;
  /** start 事件: 前驱节点 id (可能为 null = 第一个节点). */
  previous_node_id: string | null;
  /** complete 事件: 是否成功 (失败步骤才有 error_msg/error_code). */
  success: boolean | null;
  /** complete 事件: 节点耗时 (ms). */
  elapsed_ms: number;
  retry_count: number;
  /** complete 事件: 失败时的错误信息 (空字符串 = 成功). */
  error_msg: string;
  /** complete 事件: NodeErrorCode 字符串 (TIMEOUT/SCREEN_UNCHANGED/...). */
  error_code: string;
  /** 识别类节点诊断字段 (template_match / ocr 等). */
  confidence: number | null;
  threshold: number | null;
  match_location: { x: number; y: number } | null;
  roi_physical: number[] | null;
  screenshot_path: string | null;
  /** 坐标系标签 (logical / physical), N191 §10.7. */
  coord_system: string;
  /** 前驱节点 result_data 摘要, 让用户能定位 "前驱输出 → 当前输入". */
  previous_node_result_data: Record<string, unknown> | null;
  previous_node_type: string | null;
  /** 节点设计语义 (spec 阶段 4.3): comment 描述节点做什么, rationale 描述为什么这样设计. */
  comment: string;
  rationale: string;
}

/**
 * Task 2.4 (N192 B7 P1-7): 获取指定步骤的 JSONL trace.
 *
 * 用于前端 NodeDetailDrawer 展示节点详情, 让用户能自行查到 "这个节点当时配的
 * threshold/ROI 是多少" 而不必找开发查日志.
 *
 * Endpoint: GET /tasks/task-executions/{executionId}/node-trace/{stepIndex}/
 * - 200: 返回 NodeTraceData, 含 input_config / result_data / error_msg 等.
 * - 404: 文件不存在或 step_index 超出节点数, response.data 为 {code, message, data:null}.
 *
 * axios 拦截器已统一 unwrap {code:0, message, data} → data, 失败时 reject
 * 并保留 businessMessage 字段, 调用方 try/catch 处理.
 */
export async function getNodeTrace(executionId: number, stepIndex: number): Promise<NodeTraceData> {
  const res = await client.get<NodeTraceData>(`/tasks/task-executions/${executionId}/node-trace/${stepIndex}/`);
  return res.data;
}
