import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DeviceCenterPage from '@/pages/Devices/DeviceCenterPage';

const mockDeviceState = {
  agents: [] as never[],
  devices: [] as never[],
  groups: [] as never[],
  total: 0,
  loading: false,
  currentScreenshot: null,
  fetchAgents: vi.fn().mockResolvedValue(undefined),
  fetchDevices: vi.fn().mockResolvedValue(undefined),
  fetchGroups: vi.fn().mockResolvedValue(undefined),
  requestScreenshot: vi.fn(),
  setScreenshot: vi.fn(),
  clearScreenshot: vi.fn(),
  refreshAll: vi.fn().mockResolvedValue(undefined),
};

vi.mock('../../../stores/useDeviceStore', () => ({
  useDeviceStore: vi.fn(() => mockDeviceState),
}));

vi.mock('../../../api/devices', () => ({
  registerDevice: vi.fn(),
  scanDevices: vi.fn().mockResolvedValue({ total: 0, registered: 0 }),
  healthCheckDevices: vi.fn(),
  requestScreenshot: vi.fn(),
}));

vi.mock('../../../websocket/client', () => ({
  wsClient: {
    connect: vi.fn(),
    disconnect: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    send: vi.fn(),
    onMessage: vi.fn(),
    offMessage: vi.fn(),
  },
}));

describe('DeviceCenterPage', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <DeviceCenterPage />
      </MemoryRouter>,
    );
    expect(screen.getAllByText('扫描模拟器').length).toBeGreaterThan(0);
  }, 15000);
});
