/**
 * TD-336 #2: ApiKeysPage smoke 测试
 * 覆盖: 渲染不崩溃 / 页面标题 / 新建按钮打开弹窗 / 列表加载
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { ApiKeysPage } from '@/pages/System/ApiKeysPage';

// Mock accounts API
vi.mock('@/api/accounts', () => ({
  fetchApiKeys: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  createApiKey: vi.fn(),
  updateApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
  fetchAuditLogs: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ApiKeysPage', () => {
  it('应渲染页面标题且不崩溃', async () => {
    render(
      <MemoryRouter>
        <AntApp>
          <ApiKeysPage />
        </AntApp>
      </MemoryRouter>,
    );
    // 页面标题 (apiKeys.page_title = 'API Key 管理')
    await waitFor(() => {
      expect(screen.getByText('API Key 管理')).toBeDefined();
    });
  });

  it('应调用 fetchApiKeys 加载数据', async () => {
    const { fetchApiKeys } = await import('@/api/accounts');
    render(
      <MemoryRouter>
        <AntApp>
          <ApiKeysPage />
        </AntApp>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(fetchApiKeys).toHaveBeenCalled();
    });
  });

  it('点击新建按钮应打开编辑弹窗', async () => {
    render(
      <MemoryRouter>
        <AntApp>
          <ApiKeysPage />
        </AntApp>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText('API Key 管理')).toBeDefined();
    });
    // 点击 "新建 API Key" 按钮 (apiKeys.btn_create)
    // 使用 regex 匹配，因为按钮有 PlusOutlined 图标 (aria-label="plus")
    const createBtn = screen.getByRole('button', { name: /新建 API Key/ });
    fireEvent.click(createBtn);
    // 弹窗应出现 — "IP 白名单" 仅在表单中出现 (不在表格列头)
    await waitFor(() => {
      expect(screen.getByText('IP 白名单')).toBeDefined();
    });
  });
});
