/**
 * TD-336: UserManagePage smoke 测试
 * 覆盖: 渲染不崩溃 / 页面标题 / 用户列表加载
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { UserManagePage } from '@/pages/Accounts/UserManagePage';

// Mock settings API
vi.mock('@/api/settings', () => ({
  fetchUsers: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  deleteUser: vi.fn(),
  resetUserPassword: vi.fn(),
}));

// Mock accounts API
vi.mock('@/api/accounts', () => ({
  fetchLoginHistory: vi.fn().mockResolvedValue({ results: [], count: 0 }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('UserManagePage', () => {
  it('应渲染页面标题且不崩溃', async () => {
    render(
      <MemoryRouter>
        <AntApp>
          <UserManagePage />
        </AntApp>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText('用户管理')).toBeDefined();
    });
  });

  it('应调用 fetchUsers 加载数据', async () => {
    const { fetchUsers } = await import('@/api/settings');
    render(
      <MemoryRouter>
        <AntApp>
          <UserManagePage />
        </AntApp>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(fetchUsers).toHaveBeenCalled();
    });
  });
});
