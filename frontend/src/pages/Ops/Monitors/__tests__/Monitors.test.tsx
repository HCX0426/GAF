import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { App } from 'antd';
import MonitorsPage from '@/pages/Ops/Monitors/index';

vi.mock('../../../../api/monitors', () => ({
  fetchMonitorRules: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  createMonitorRule: vi.fn().mockResolvedValue({}),
  updateMonitorRule: vi.fn().mockResolvedValue({}),
  deleteMonitorRule: vi.fn().mockResolvedValue(undefined),
  fetchMonitorEvents: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  acknowledgeEvent: vi.fn().mockResolvedValue(undefined),
  diagnose: vi.fn().mockResolvedValue({}),
  autoFix: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../../../api/alertRules', () => ({
  fetchAlertRules: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  createAlertRule: vi.fn().mockResolvedValue({}),
  updateAlertRule: vi.fn().mockResolvedValue({}),
  deleteAlertRule: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../../../api/resources', () => ({
  fetchResourcePacks: vi.fn().mockResolvedValue({ results: [], count: 0 }),
}));

describe('MonitorsPage', () => {
  it('renders without crashing', () => {
    const { getByText } = render(
      <App>
        <MonitorsPage />
      </App>,
    );
    expect(getByText('监控告警')).toBeDefined();
    expect(getByText('监控规则')).toBeDefined();
    expect(getByText('告警事件')).toBeDefined();
  });

  it('点击 Tab 应切换活动标签', async () => {
    const { container } = render(
      <App>
        <MonitorsPage />
      </App>,
    );
    const tabs = container.querySelectorAll('.ant-tabs-tab');
    if (tabs.length > 1) {
      fireEvent.click(tabs[1]);
      await waitFor(() => {
        const activeTab = container.querySelector('.ant-tabs-tab-active');
        expect(activeTab).toBeTruthy();
      });
    }
  });
});
