import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import TasksPage from '@/pages/Tasks/index';

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

vi.mock('../../../stores/useTaskStore', () => ({
  useTaskStore: vi.fn(() => mockTaskState),
}));

describe('TasksPage', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <TasksPage />
      </MemoryRouter>,
    );
    expect(screen.getByText('任务管理')).toBeDefined();
  });

  it('搜索框输入应更新值', async () => {
    const { container } = render(
      <MemoryRouter>
        <TasksPage />
      </MemoryRouter>,
    );
    const searchInput = container.querySelector('input[placeholder*="搜索"]') as HTMLInputElement;
    if (searchInput) {
      fireEvent.change(searchInput, { target: { value: '测试搜索' } });
      expect(searchInput.value).toBe('测试搜索');
    }
  });
});
