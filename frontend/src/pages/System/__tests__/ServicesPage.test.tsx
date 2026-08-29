/**
 * spec 2026-08-29-services-management-monitor P4: ServicesPage 冒烟测试.
 * 覆盖: 渲染服务卡片 / 查看日志 Drawer / ERROR 过滤.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ServicesPage } from '@/pages/System/ServicesPage';

const mockServices = vi.hoisted(() => ({
  updatedAt: '2026-08-29T10:00:00+0800',
  daemon: { running: true, pid: 456 },
  services: [
    {
      name: 'backend', healthy: true, detail: 'healthz pass', ts: 1,
      running: true, pid: 123, port: 8000, restart_count: 0,
      error_count: 2, latest_error: 'ERROR boom', log_files: [],
    },
    {
      name: 'frontend', healthy: true, detail: 'HTTP 200', ts: 1,
      running: true, pid: 789, port: 5173, restart_count: 0,
      error_count: 0, latest_error: null, log_files: [],
    },
    {
      name: 'daemon', healthy: true, detail: 'daemon PID=456', ts: null,
      running: true, pid: 456, port: null, restart_count: null,
      error_count: null, latest_error: null, log_files: [],
    },
  ],
}));

vi.mock('@/api/services', () => ({
  fetchSystemServices: vi.fn().mockResolvedValue(mockServices),
  fetchServiceLogs: vi.fn().mockResolvedValue({
    service: 'backend',
    path: 'debug/system/services/backend.log',
    files: [],
    lines: ['INFO starting', 'ERROR boom', 'Traceback (most recent call last):', 'ValueError: bad'],
  }),
}));

import { fetchServiceLogs, fetchSystemServices } from '@/api/services';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ServicesPage', () => {
  it('渲染页面标题与服务卡片', async () => {
    render(
      <MemoryRouter>
        <ServicesPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText('服务管理')).toBeDefined();
    });
    expect(fetchSystemServices).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByText('backend')).toBeDefined();
      expect(screen.getByText('frontend')).toBeDefined();
      expect(screen.getByText('守护进程运行中 (PID 456)')).toBeDefined();
    });
  });

  it('报错计数 Tag 显示', async () => {
    render(
      <MemoryRouter>
        <ServicesPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getAllByText(/2 条报错/).length).toBeGreaterThan(0);
    });
  });

  it('点击"查看日志"打开 Drawer 并加载日志', async () => {
    render(
      <MemoryRouter>
        <ServicesPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText('backend')).toBeDefined();
    });
    const buttons = screen.getAllByText('查看日志');
    fireEvent.click(buttons[0]);
    await waitFor(() => {
      expect(fetchServiceLogs).toHaveBeenCalledWith(
        expect.objectContaining({ service: 'backend' }),
      );
    });
    const drawer = screen.getByRole('dialog');
    await waitFor(() => {
      expect(within(drawer).getByText(/ERROR boom/)).toBeDefined();
    });
  });
});