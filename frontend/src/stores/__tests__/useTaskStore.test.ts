import { describe, it, expect, beforeEach } from 'vitest';
import { useTaskStore } from '@/stores/useTaskStore';

describe('taskStore', () => {
  beforeEach(() => {
    useTaskStore.setState({
      tasks: [],
      total: 0,
      loading: false,
      currentExecution: null,
      executionLog: [],
    });
  });

  it('初始状态应为空任务列表', () => {
    const state = useTaskStore.getState();
    expect(state.tasks).toEqual([]);
    expect(state.currentExecution).toBeNull();
    expect(state.loading).toBe(false);
    expect(state.executionLog).toEqual([]);
  });

  it('addExecutionLog 应添加日志条目', () => {
    const { addExecutionLog } = useTaskStore.getState();
    addExecutionLog('任务 1 开始执行');

    const state = useTaskStore.getState();
    expect(state.executionLog).toHaveLength(1);
    expect(state.executionLog[0]).toContain('任务 1 开始执行');
  });

  it('addExecutionLog 应追加而非覆盖', () => {
    const { addExecutionLog } = useTaskStore.getState();
    addExecutionLog('第一条日志');
    addExecutionLog('第二条日志');

    const state = useTaskStore.getState();
    expect(state.executionLog).toHaveLength(2);
    expect(state.executionLog[0]).toContain('第一条日志');
    expect(state.executionLog[1]).toContain('第二条日志');
  });

  it('clearExecutionLog 应清空日志', () => {
    const { addExecutionLog, clearExecutionLog } = useTaskStore.getState();
    addExecutionLog('日志 A');
    addExecutionLog('日志 B');
    expect(useTaskStore.getState().executionLog).toHaveLength(2);

    clearExecutionLog();
    expect(useTaskStore.getState().executionLog).toEqual([]);
  });
});
