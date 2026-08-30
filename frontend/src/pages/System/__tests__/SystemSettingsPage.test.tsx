/**
 * TD-336: SystemSettingsPage smoke 测试
 * 覆盖: 渲染不崩溃
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SystemSettingsPage } from '@/pages/System/SystemSettings';

// Mock settings API
vi.mock('@/api/settings', () => ({
  fetchTaskStats: vi.fn().mockResolvedValue({}),
  cleanupData: vi.fn(),
  generateDiagnosticPack: vi.fn(),
  fetchWorkerDebug: vi.fn().mockResolvedValue({}),
  updateWorkerDebug: vi.fn(),
  fetchWindowBackgroundWait: vi.fn().mockResolvedValue({}),
  updateWindowBackgroundWait: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SystemSettingsPage', () => {
  it('应渲染且不崩溃', async () => {
    render(
      <MemoryRouter>
        <SystemSettingsPage />
      </MemoryRouter>,
    );
    // 页面标题 (settings.page_title)
    await waitFor(() => {
      expect(screen.getByText('系统设置')).toBeDefined();
    });
  });
});
