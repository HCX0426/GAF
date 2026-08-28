/**
 * TD-336 #2: AuditLogPage smoke 测试
 * 覆盖: 渲染不崩溃 / 页面标题 / 列表加载 / 搜索框输入
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuditLogPage } from '@/pages/System/AuditLogPage';

// Mock accounts API — 返回空列表避免渲染复杂表格
vi.mock('@/api/accounts', () => ({
  fetchAuditLogs: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  fetchApiKeys: vi.fn(),
  createApiKey: vi.fn(),
  updateApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AuditLogPage', () => {
  it('应渲染页面标题且不崩溃', async () => {
    render(
      <MemoryRouter>
        <AuditLogPage />
      </MemoryRouter>,
    );
    // 页面标题 (auditLog.page_title)
    await waitFor(() => {
      expect(screen.getByText('审计日志')).toBeDefined();
    });
  });

  it('应调用 fetchAuditLogs 加载数据', async () => {
    const { fetchAuditLogs } = await import('@/api/accounts');
    render(
      <MemoryRouter>
        <AuditLogPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(fetchAuditLogs).toHaveBeenCalled();
    });
  });

  it('搜索框输入应更新值', async () => {
    const { container } = render(
      <MemoryRouter>
        <AuditLogPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText('审计日志')).toBeDefined();
    });
    // 搜索框 (auditLog.search_placeholder)
    const searchInput = container.querySelector('input[placeholder*="搜索"]') as HTMLInputElement;
    expect(searchInput).not.toBeNull();
    fireEvent.change(searchInput, { target: { value: 'test-query' } });
    expect(searchInput.value).toBe('test-query');
  });

  it('点击刷新按钮应重新加载数据', async () => {
    const { fetchAuditLogs } = await import('@/api/accounts');
    render(
      <MemoryRouter>
        <AuditLogPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(fetchAuditLogs).toHaveBeenCalledTimes(1);
    });
    // 点击刷新按钮 (auditLog.btn_refresh -> "刷新")
    // 使用 regex 匹配，因为按钮有 ReloadOutlined 图标 (aria-label="reload")
    const refreshBtn = screen.getByRole('button', { name: /刷新/ });
    fireEvent.click(refreshBtn);
    await waitFor(() => {
      expect(fetchAuditLogs).toHaveBeenCalledTimes(2);
    });
  });
});
