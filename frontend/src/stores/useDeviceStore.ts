/**
 * device status management Store
 * management Device list, group, screenshot,Agent list,WebSocket reconnect recover
 * Phase 3 additions: scan, register, test screenshot, lock/unlock, stats, compatibility check
 */
import { create } from 'zustand';
import { wsClient } from '@/websocket/client';
import { fetchAgents as apiFetchAgents } from '@/api/agents';
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
  scanDevices as apiScanDevices,
  registerDevice as apiRegisterDevice,
  testScreenshot as apiTestScreenshot,
  lockDevice as apiLockDevice,
  unlockDevice as apiUnlockDevice,
  fetchDeviceStats as apiFetchDeviceStats,
  checkCompatibility as apiCheckCompatibility,
} from '@/api/devices';
import type {
  Worker,
  Device,
  DeviceGroup,
  ScreenshotResponse,
  ScanResponse,
  ScreenshotTestResult,
  LockResponse,
  DeviceStats,
  CompatibilityCheckResult,
  DeviceRegisterParams,
} from '@/types/models';

/** device Store status API */
interface DeviceState {
  agents: Worker[];
  devices: Device[];
  groups: DeviceGroup[];
  total: number;
  loading: boolean;
  currentScreenshot: ScreenshotResponse | null;

  fetchAgents: (page?: number, pageSize?: number) => Promise<void>;
  fetchDevices: (params?: Record<string, unknown>) => Promise<void>;
  fetchGroups: () => Promise<void>;
  createDevice: (data: Partial<Device>) => Promise<Device>;
  updateDevice: (id: number, data: Partial<Device>) => Promise<Device>;
  deleteDevice: (id: number) => Promise<void>;
  createGroup: (data: { name: string; devices?: number[]; parent?: number }) => Promise<DeviceGroup>;
  updateGroup: (id: number, data: { name?: string; devices?: number[]; parent?: number }) => Promise<DeviceGroup>;
  deleteGroup: (id: number) => Promise<void>;
  requestScreenshot: (deviceId: number) => Promise<void>;
  clearScreenshot: () => void;
  refreshAll: () => Promise<void>;

  scanDevices: (type?: 'android' | 'windows' | 'all') => Promise<ScanResponse>;
  registerDevice: (data: DeviceRegisterParams) => Promise<Device>;
  testScreenshot: (deviceId: number, method?: string) => Promise<ScreenshotTestResult>;
  lockDevice: (deviceId: number, force?: boolean) => Promise<LockResponse>;
  unlockDevice: (deviceId: number, force?: boolean) => Promise<LockResponse>;
  getStats: (deviceId: number) => Promise<DeviceStats>;
  checkCompatibility: (deviceId: number, packId: string) => Promise<CompatibilityCheckResult>;

  /**
   * Subscribe the store to WebSocket device events. Call once at app boot.
   * Re-fetches the device list when a device.updated / device.registered /
   * device.metrics_updated event arrives, so open device cards stay in sync
   * without per-page visibilitychange polling.
   *
   * Returns an unsubscribe function (mainly for tests).
   */
  subscribeToDeviceUpdates: () => () => void;
}

/** device status management */
export const useDeviceStore = create<DeviceState>((set, get) => ({
  agents: [],
  devices: [],
  groups: [],
  total: 0,
  loading: false,
  currentScreenshot: null,

  /** get Agent list */
  fetchAgents: async (page = 1, pageSize = 50) => {
    set({ loading: true });
    try {
      const res = await apiFetchAgents({ page, page_size: pageSize });
      set({ agents: res.results || [], loading: false });
    } catch {
      set({ loading: false });
    }
  },

  /** get device list */
  fetchDevices: async (params) => {
    set({ loading: true });
    try {
      const res = await apiFetchDevices(params);
      const devices = res.results || [];
      const total = res.count || 0;
      set({ devices: devices as Device[], total, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  /** get device group */
  fetchGroups: async () => {
    try {
      const res = await apiFetchGroups();
      set({ groups: (res.results || []) as DeviceGroup[] });
    } catch {
      // silent failure
    }
  },

  /** register device */
  createDevice: async (data) => {
    const device = await apiCreateDevice(data);
    set((state) => ({ devices: [device, ...state.devices] }));
    return device;
  },

  /** update device */
  updateDevice: async (id, data) => {
    const device = await apiUpdateDevice(id, data);
    set((state) => ({
      devices: state.devices.map((d) => (d.id === id ? device : d)),
    }));
    return device;
  },

  /** delete device */
  deleteDevice: async (id) => {
    await apiDeleteDevice(id);
    set((state) => ({
      devices: state.devices.filter((d) => d.id !== id),
    }));
  },

  /** create device group */
  createGroup: async (data) => {
    const group = await apiCreateGroup(data);
    set((state) => ({ groups: [...state.groups, group] }));
    return group;
  },

  /** update device group */
  updateGroup: async (id, data) => {
    const group = await apiUpdateGroup(id, data);
    set((state) => ({
      groups: state.groups.map((g) => (g.id === id ? group : g)),
    }));
    return group;
  },

  /** delete device group */
  deleteGroup: async (id) => {
    await apiDeleteGroup(id);
    set((state) => ({
      groups: state.groups.filter((g) => g.id !== id),
    }));
  },

  /** request specified device screenshot */
  requestScreenshot: async (deviceId: number) => {
    try {
      const screenshot = await apiRequestScreenshot(deviceId);
      set({ currentScreenshot: screenshot });
    } catch {
      throw new Error('SCREENSHOT_FETCH_FAILED');
    }
  },

  /** settings screenshot data ( by WebSocket callback trigger ) */
  setScreenshot: (screenshot: ScreenshotResponse | null) => {
    set({ currentScreenshot: screenshot });
  },

  /** clear current screenshot data */
  clearScreenshot: () => {
    set({ currentScreenshot: null });
  },

  /** refresh has device data, used for WebSocket reconnect after status recover */
  refreshAll: async () => {
    try {
      await Promise.all([get().fetchAgents(), get().fetchDevices(), get().fetchGroups()]);
    } catch {
      // Refresh after WS reconnect failed — UI will show stale data until next manual refresh
    }
  },

  /** Phase 3 — scan devices */
  scanDevices: async (type = 'all') => {
    return apiScanDevices(type);
  },

  /** Phase 3 — register device */
  registerDevice: async (data) => {
    const device = await apiRegisterDevice(data);
    set((state) => ({ devices: [device, ...state.devices] }));
    return device;
  },

  /** Phase 3 — test screenshot.
   *  After a successful test, updates the specific device in the store so the
   *  DeviceCard immediately reflects the new latency/FPS without a full refetch.
   *  The backend also persists these metrics to device_stats.screenshot_latency_avg_ms,
   *  so subsequent list fetches stay consistent.
   */
  testScreenshot: async (deviceId, method) => {
    const result = await apiTestScreenshot(deviceId, method);
    if (result.success) {
      set((state) => ({
        devices: state.devices.map((d) => {
          if (d.id !== deviceId) return d;
          return {
            ...d,
            screenshot_fps: result.fps,
            screenshot_method: result.screenshot_method,
            device_stats: {
              ...(d.device_stats || {}),
              screenshot_latency_avg_ms: result.latency_ms,
              screenshot_fps: result.fps,
              screenshot_method: result.screenshot_method,
            },
          };
        }),
      }));
    }
    return result;
  },

  /** Phase 3 — lock device */
  lockDevice: async (deviceId, force) => {
    const result = await apiLockDevice(deviceId, force);
    await get().fetchDevices();
    return result;
  },

  /** Phase 3 — unlock device */
  unlockDevice: async (deviceId, force) => {
    const result = await apiUnlockDevice(deviceId, force);
    await get().fetchDevices();
    return result;
  },

  /** Phase 3 — get device stats */
  getStats: async (deviceId) => {
    return apiFetchDeviceStats(deviceId);
  },

  /** Phase 3 — check compatibility */
  checkCompatibility: async (deviceId, packId) => {
    return apiCheckCompatibility(deviceId, Number(packId));
  },

  /**
   * Subscribe to device.* WebSocket events and refresh the device list on
   * any change. We deliberately re-fetch the full list (rather than patching
   * a single device) because the backend serialiser computes derived fields
   * (device_stats, available_methods, group membership) that we cannot
   * reliably reconstruct on the client. The list endpoint is paginated and
   * cheap, and these events are low-frequency (user-driven, not per-frame).
   *
   * Subscribers that need the very latest single-device data should still
   * call fetchDevices() themselves; this subscription only guarantees that
   * background changes from other tabs/windows propagate.
   */
  subscribeToDeviceUpdates: () => {
    const types = ['device.updated', 'device.registered', 'device.metrics_updated', 'device.capabilities_updated'];
    const handlers: Array<(data: Record<string, unknown>) => void> = [];
    let refetchTimer: number | null = null;
    for (const type of types) {
      const handler = () => {
        // Debounce: collapse rapid bursts (e.g. screenshot test + metrics
        // update fired back-to-back) into a single refetch.
        if (refetchTimer) return;
        refetchTimer = window.setTimeout(() => {
          refetchTimer = null;
          void get().fetchDevices();
        }, 200);
      };
      handlers.push(handler);
      wsClient.onMessage(type, handler);
    }
    return () => {
      if (refetchTimer) {
        window.clearTimeout(refetchTimer);
        refetchTimer = null;
      }
      types.forEach((type, i) => wsClient.offMessage(type, handlers[i]));
    };
  },
}));
