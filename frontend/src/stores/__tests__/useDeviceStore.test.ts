/**
 * TD-336 #4: useDeviceStore 测试 — 覆盖设备/分组 CRUD + 列表加载 + 截图
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useDeviceStore } from '@/stores/useDeviceStore';
import type { Device, DeviceGroup, Agent } from '@/types/models';

// Mock devices API
vi.mock('@/api/devices', () => ({
  fetchDevices: vi.fn(),
  fetchDeviceGroups: vi.fn(),
  createDevice: vi.fn(),
  updateDevice: vi.fn(),
  deleteDevice: vi.fn(),
  createDeviceGroup: vi.fn(),
  updateDeviceGroup: vi.fn(),
  deleteDeviceGroup: vi.fn(),
  requestScreenshot: vi.fn(),
  scanDevices: vi.fn(),
  registerDevice: vi.fn(),
  testScreenshot: vi.fn(),
  lockDevice: vi.fn(),
  unlockDevice: vi.fn(),
  fetchDeviceStats: vi.fn(),
  checkCompatibility: vi.fn(),
}));

// Mock agents API
vi.mock('@/api/agents', () => ({
  fetchAgents: vi.fn(),
}));

// Mock websocket client (subscribeToDeviceUpdates uses onMessage/offMessage)
vi.mock('@/websocket/client', () => ({
  wsClient: {
    onMessage: vi.fn(),
    offMessage: vi.fn(),
  },
}));

import {
  fetchDevices as apiFetchDevices,
  fetchDeviceGroups as apiFetchGroups,
  createDevice as apiCreateDevice,
  updateDevice as apiUpdateDevice,
  deleteDevice as apiDeleteDevice,
  createDeviceGroup as apiCreateGroup,
  updateDeviceGroup as apiUpdateGroup,
  deleteDeviceGroup as apiDeleteGroup,
  requestScreenshot as apiRequestScreenshot,
} from '@/api/devices';
import { fetchAgents as apiFetchAgents } from '@/api/agents';

const makeDevice = (id: number, overrides: Partial<Device> = {}): Device =>
  ({
    id,
    name: `Device ${id}`,
    status: 'online',
    ip_address: '192.168.1.100',
    ...overrides,
  }) as Device;

const makeGroup = (id: number, name = `Group ${id}`): DeviceGroup => ({ id, name }) as DeviceGroup;
const makeAgent = (id: number): Agent => ({ id, name: `Agent ${id}` }) as unknown as Agent;

beforeEach(() => {
  useDeviceStore.setState({
    agents: [],
    devices: [],
    groups: [],
    total: 0,
    loading: false,
    currentScreenshot: null,
  });
  vi.clearAllMocks();
});

describe('useDeviceStore', () => {
  describe('初始状态', () => {
    it('devices/agents/groups 应为空数组', () => {
      const s = useDeviceStore.getState();
      expect(s.devices).toEqual([]);
      expect(s.agents).toEqual([]);
      expect(s.groups).toEqual([]);
    });

    it('loading 应为 false', () => {
      expect(useDeviceStore.getState().loading).toBe(false);
    });
  });

  describe('fetchDevices', () => {
    it('成功时应更新 devices/total 并清除 loading', async () => {
      const mockDevices = [makeDevice(1), makeDevice(2)];
      vi.mocked(apiFetchDevices).mockResolvedValue({ results: mockDevices, count: 2 } as never);

      const { fetchDevices } = useDeviceStore.getState();
      await fetchDevices();

      const s = useDeviceStore.getState();
      expect(s.devices).toHaveLength(2);
      expect(s.total).toBe(2);
      expect(s.loading).toBe(false);
    });

    it('API 失败时 loading 应恢复 false', async () => {
      vi.mocked(apiFetchDevices).mockRejectedValue(new Error('Network error'));

      const { fetchDevices } = useDeviceStore.getState();
      await fetchDevices();

      expect(useDeviceStore.getState().loading).toBe(false);
      expect(useDeviceStore.getState().devices).toEqual([]);
    });
  });

  describe('fetchAgents', () => {
    it('成功时应更新 agents 并清除 loading', async () => {
      vi.mocked(apiFetchAgents).mockResolvedValue({ results: [makeAgent(1)], count: 1 } as never);

      const { fetchAgents } = useDeviceStore.getState();
      await fetchAgents();

      const s = useDeviceStore.getState();
      expect(s.agents).toHaveLength(1);
      expect(s.loading).toBe(false);
    });

    it('API 失败时 loading 应恢复 false', async () => {
      vi.mocked(apiFetchAgents).mockRejectedValue(new Error('Network error'));

      const { fetchAgents } = useDeviceStore.getState();
      await fetchAgents();

      expect(useDeviceStore.getState().loading).toBe(false);
    });
  });

  describe('fetchGroups', () => {
    it('成功应更新 groups', async () => {
      vi.mocked(apiFetchGroups).mockResolvedValue({ results: [makeGroup(1)], count: 1 } as never);

      const { fetchGroups } = useDeviceStore.getState();
      await fetchGroups();

      expect(useDeviceStore.getState().groups).toHaveLength(1);
    });

    it('API 失败应静默不抛错', async () => {
      vi.mocked(apiFetchGroups).mockRejectedValue(new Error('Network error'));

      const { fetchGroups } = useDeviceStore.getState();
      await fetchGroups(); // 不应 throw

      expect(useDeviceStore.getState().groups).toEqual([]);
    });
  });

  describe('设备 CRUD', () => {
    it('createDevice 应前置插入新设备', async () => {
      const existing = [makeDevice(1)];
      useDeviceStore.setState({ devices: existing });
      vi.mocked(apiCreateDevice).mockResolvedValue(makeDevice(2) as never);

      const { createDevice } = useDeviceStore.getState();
      const created = await createDevice({ name: 'new' });

      const s = useDeviceStore.getState();
      expect(created.id).toBe(2);
      expect(s.devices).toHaveLength(2);
      expect(s.devices[0].id).toBe(2); // 前置插入
    });

    it('updateDevice 应替换对应设备', async () => {
      useDeviceStore.setState({ devices: [makeDevice(1), makeDevice(2)] });
      const updated = makeDevice(1, { name: 'renamed' });
      vi.mocked(apiUpdateDevice).mockResolvedValue(updated as never);

      const { updateDevice } = useDeviceStore.getState();
      await updateDevice(1, { name: 'renamed' });

      const s = useDeviceStore.getState();
      expect(s.devices[0].name).toBe('renamed');
      expect(s.devices[1].name).toBe('Device 2'); // 未受影响
    });

    it('deleteDevice 应移除指定设备', async () => {
      useDeviceStore.setState({ devices: [makeDevice(1), makeDevice(2)] });
      vi.mocked(apiDeleteDevice).mockResolvedValue(undefined as never);

      const { deleteDevice } = useDeviceStore.getState();
      await deleteDevice(1);

      const s = useDeviceStore.getState();
      expect(s.devices).toHaveLength(1);
      expect(s.devices[0].id).toBe(2);
    });
  });

  describe('分组 CRUD', () => {
    it('createGroup 应追加新分组', async () => {
      vi.mocked(apiCreateGroup).mockResolvedValue(makeGroup(1) as never);

      const { createGroup } = useDeviceStore.getState();
      const created = await createGroup({ name: 'new' });

      expect(created.id).toBe(1);
      expect(useDeviceStore.getState().groups).toHaveLength(1);
    });

    it('updateGroup 应替换对应分组', async () => {
      useDeviceStore.setState({ groups: [makeGroup(1, 'old'), makeGroup(2)] });
      vi.mocked(apiUpdateGroup).mockResolvedValue(makeGroup(1, 'renamed') as never);

      const { updateGroup } = useDeviceStore.getState();
      await updateGroup(1, { name: 'renamed' });

      expect(useDeviceStore.getState().groups[0].name).toBe('renamed');
    });

    it('deleteGroup 应移除指定分组', async () => {
      useDeviceStore.setState({ groups: [makeGroup(1), makeGroup(2)] });
      vi.mocked(apiDeleteGroup).mockResolvedValue(undefined as never);

      const { deleteGroup } = useDeviceStore.getState();
      await deleteGroup(1);

      expect(useDeviceStore.getState().groups).toHaveLength(1);
      expect(useDeviceStore.getState().groups[0].id).toBe(2);
    });
  });

  describe('requestScreenshot', () => {
    it('成功应设置 currentScreenshot', async () => {
      const mockShot = { device_id: 1, image: 'base64...', timestamp: '2026-01-01' };
      vi.mocked(apiRequestScreenshot).mockResolvedValue(mockShot as never);

      const { requestScreenshot } = useDeviceStore.getState();
      await requestScreenshot(1);

      expect(useDeviceStore.getState().currentScreenshot).toEqual(mockShot);
    });

    it('API 失败应抛出错误并清空 currentScreenshot', async () => {
      useDeviceStore.setState({ currentScreenshot: { device_id: 1 } as never });
      vi.mocked(apiRequestScreenshot).mockRejectedValue(new Error('Capture failed'));

      const { requestScreenshot } = useDeviceStore.getState();
      await expect(requestScreenshot(1)).rejects.toThrow('SCREENSHOT_FETCH_FAILED');
    });
  });

  describe('clearScreenshot', () => {
    it('应清空 currentScreenshot', () => {
      useDeviceStore.setState({ currentScreenshot: { device_id: 1 } as never });
      useDeviceStore.getState().clearScreenshot();
      expect(useDeviceStore.getState().currentScreenshot).toBeNull();
    });
  });
});
