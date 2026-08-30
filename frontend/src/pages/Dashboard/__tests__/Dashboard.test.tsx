import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DashboardPage from '@/pages/Dashboard/index';

const mockDeviceState = {
  agents: [] as never[],
  devices: [] as never[],
  total: 0,
  loading: false,
  currentScreenshot: null,
  fetchAgents: vi.fn().mockResolvedValue(undefined),
  fetchDevices: vi.fn().mockResolvedValue(undefined),
  requestScreenshot: vi.fn(),
  setScreenshot: vi.fn(),
  clearScreenshot: vi.fn(),
  refreshAll: vi.fn().mockResolvedValue(undefined),
};

const mockTaskState = {
  tasks: [] as never[],
  total: 0,
  loading: false,
  currentExecution: null,
  executionLog: [] as string[],
  fetchTasks: vi.fn().mockResolvedValue(undefined),
  executeTask: vi.fn().mockResolvedValue(undefined),
  cancelTask: vi.fn().mockResolvedValue(undefined),
  fetchExecutions: vi.fn().mockResolvedValue([]),
  fetchExecution: vi.fn().mockResolvedValue(null),
  addExecutionLog: vi.fn(),
  clearExecutionLog: vi.fn(),
  refreshAll: vi.fn().mockResolvedValue(undefined),
};

vi.mock('../../../stores/useDeviceStore', () => ({
  useDeviceStore: vi.fn(() => mockDeviceState),
}));

vi.mock('../../../stores/useTaskStore', () => ({
  useTaskStore: vi.fn(() => mockTaskState),
}));

vi.mock('../../../api/tasks', () => ({
  fetchExecutions: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  getDashboardDailyReport: vi.fn().mockResolvedValue(null),
}));

vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    connected: false,
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    send: vi.fn(),
  })),
}));

describe('DashboardPage', () => {
  it('renders without crashing', async () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText('在线 Worker')).toBeDefined();
      expect(screen.getByText('运行任务')).toBeDefined();
      expect(screen.getByText('今日执行')).toBeDefined();
      expect(screen.getByText('成功率')).toBeDefined();
      expect(screen.getByText('最近执行')).toBeDefined();
      expect(screen.getByText('Worker 健康面板')).toBeDefined();
    });
  });
});
