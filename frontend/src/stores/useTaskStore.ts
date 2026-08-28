/**
 * task status management Store
 * management task list, execute record, execute log
 */
import { create } from 'zustand';
import {
  fetchTasks as apiFetchTasks,
  executeTask as apiExecuteTask,
  cancelTask as apiCancelTask,
  fetchExecutions as apiFetchExecutions,
  fetchExecution as apiFetchExecution,
  fetchExecutionSteps as apiFetchExecutionSteps,
} from '@/api/tasks';
import { getLastTraceId } from '@/utils/traceId';
import type { Task, TaskExecution } from '@/types/models';

export interface FetchTasksParams {
  page?: number;
  page_size?: number;
  /** N197-8: filter by resource pack id */
  resource_pack?: number;
  [key: string]: unknown;
}

interface TaskState {
  tasks: Task[];
  total: number;
  loading: boolean;
  currentExecution: TaskExecution | null;
  executionLog: string[];
  fetchTasks: (params?: FetchTasksParams) => Promise<void>;
  executeTask: (taskId: number, params?: Record<string, unknown>) => Promise<void>;
  cancelTask: (taskId: number) => Promise<void>;
  fetchExecutions: (taskId?: string) => Promise<TaskExecution[]>;
  fetchExecution: (executionId: string) => Promise<TaskExecution>;
  addExecutionLog: (log: string) => void;
  clearExecutionLog: () => void;
  refreshAll: () => Promise<void>;
}

/** Internal AbortController for fetchTasks, cancels previous in-flight request */
let _fetchTasksAbortController: AbortController | null = null;

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: [],
  total: 0,
  loading: false,
  currentExecution: null,
  executionLog: [],

  fetchTasks: async (params?: FetchTasksParams) => {
    // Abort previous in-flight request
    _fetchTasksAbortController?.abort();
    const controller = new AbortController();
    _fetchTasksAbortController = controller;

    set({ loading: true });
    try {
      const res = await apiFetchTasks({ ...(params || {}), signal: controller.signal });
      if (controller.signal.aborted) return;
      const tasks = res.results || [];
      const total = res.count || 0;
      set({ tasks, total, loading: false });
    } catch (error) {
      // axios aborts surface as CanceledError (code ERR_CANCELED), not the
      // native AbortError — treat both as expected cancels (newer fetchTasks
      // superseded this one), not real failures.
      const e = error as { name?: string; code?: string } | null;
      if (e?.name === 'AbortError' || e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return;
      set({ loading: false });
      throw error;
    }
  },

  executeTask: async (taskId: number, params?: Record<string, unknown>) => {
    set({ loading: true, executionLog: [] });
    try {
      const execution = await apiExecuteTask(taskId, params);
      set({ currentExecution: execution, loading: false });
      // C1: 在执行日志中显示 trace_id, 方便用户/AI 用 trace_id 关联后端日志 (N192 调试视角)
      const traceId = getLastTraceId();
      get().addExecutionLog(
        `任务 ${taskId} 开始执行，执行ID: ${execution.id}${traceId ? `，trace_id: ${traceId}` : ''}`,
      );
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  cancelTask: async (taskId: number) => {
    await apiCancelTask(taskId);
    set({ currentExecution: null });
    get().addExecutionLog(`任务 ${taskId} 已取消`);
  },

  fetchExecutions: async (taskId?: string) => {
    const res = await apiFetchExecutions(taskId ? { task: Number(taskId) } : {});
    return res.results || [];
  },

  fetchExecution: async (executionId: string) => {
    const execution = await apiFetchExecution(Number(executionId));
    return execution;
  },

  addExecutionLog: (log: string) => {
    set((state) => ({
      executionLog: [...state.executionLog, `[${new Date().toLocaleTimeString()}] ${log}`],
    }));
  },

  clearExecutionLog: () => {
    set({ executionLog: [] });
  },

  refreshAll: async () => {
    try {
      await get().fetchTasks();
      const execution = get().currentExecution;
      if (execution) {
        await apiFetchExecutionSteps(execution.id);
      }
    } catch {
      // Task refresh failed — UI will keep existing data
    }
  },
}));
