import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { App } from 'antd';
import ResourcesPage from '@/pages/Resources/index';
import { fetchResourcePacks } from '../../../api/resources';

vi.mock('../../../api/resources', () => ({
  fetchResourcePacks: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  activateResourcePack: vi.fn().mockResolvedValue({}),
  deactivateResourcePack: vi.fn().mockResolvedValue(undefined),
  importResourcePack: vi.fn().mockResolvedValue(undefined),
  exportResourcePack: vi.fn().mockResolvedValue(new Blob()),
  deleteResourcePack: vi.fn().mockResolvedValue(undefined),
  scanResourcePacks: vi.fn().mockResolvedValue({ total: 0, success: 0, failed: 0, results: [] }),
  createResourcePack: vi.fn().mockResolvedValue({}),
  fetchResourcePackVersionHistory: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../../api/accounts', () => ({
  fetchGameOptions: vi.fn().mockResolvedValue({ games: [] }),
}));

describe('ResourcesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders without crashing', () => {
    const { getByText } = render(
      <App>
        <ResourcesPage />
      </App>,
    );
    expect(getByText('资源包管理')).toBeDefined();
    expect(getByText('导入')).toBeDefined();
    expect(getByText('刷新')).toBeDefined();
  });

  it('点击刷新按钮应触发 fetchResourcePacks', async () => {
    const { getByText } = render(
      <App>
        <ResourcesPage />
      </App>,
    );
    vi.clearAllMocks();
    const refreshButton = getByText('刷新');
    fireEvent.click(refreshButton);
    await waitFor(() => {
      expect(fetchResourcePacks).toHaveBeenCalled();
    });
  });
});
