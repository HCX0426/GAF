/**
 * TD-336: NotificationsPage smoke 测试
 * 覆盖: 渲染不崩溃
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { NotificationsPage } from '@/pages/System/Notifications';

// Mock notifications API
vi.mock('@/api/notifications', () => ({
  fetchNotifications: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  fetchUnreadCount: vi.fn().mockResolvedValue(0),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  deleteNotification: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('NotificationsPage', () => {
  it('应渲染且不崩溃', async () => {
    render(
      <MemoryRouter>
        <AntApp>
          <NotificationsPage />
        </AntApp>
      </MemoryRouter>,
    );
    // 页面标题 (notifications.page_title)
    await waitFor(() => {
      expect(screen.getByText('通知中心')).toBeDefined();
    });
  });
});
