/**
 * TD-336 #2: Backup 页面 smoke 测试
 * 覆盖: 渲染不崩溃 / 页面标题 / 创建备份按钮 / 恢复按钮可见
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { BackupPage } from '@/pages/Ops/Backup';

// Mock ops API
vi.mock('@/api/ops', () => ({
  createBackup: vi.fn(),
  restoreBackup: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BackupPage', () => {
  it('应渲染页面标题且不崩溃', async () => {
    render(
      <MemoryRouter>
        <AntApp>
          <BackupPage />
        </AntApp>
      </MemoryRouter>,
    );
    // 页面标题 (backup.page_title = '备份与恢复')
    await waitFor(() => {
      expect(screen.getByText('备份与恢复')).toBeDefined();
    });
  });

  it('应显示创建备份卡片和按钮', async () => {
    render(
      <MemoryRouter>
        <AntApp>
          <BackupPage />
        </AntApp>
      </MemoryRouter>,
    );
    await waitFor(() => {
      // 创建按钮 (backup.btn_create = '创建全量备份')
      expect(screen.getByText('创建全量备份')).toBeDefined();
    });
  });

  it('应显示恢复备份按钮', async () => {
    render(
      <MemoryRouter>
        <AntApp>
          <BackupPage />
        </AntApp>
      </MemoryRouter>,
    );
    await waitFor(() => {
      // 恢复按钮 (backup.btn_restore = '上传备份文件并恢复')
      expect(screen.getByText('上传备份文件并恢复')).toBeDefined();
    });
  });
});
