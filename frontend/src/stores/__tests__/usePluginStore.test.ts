/**
 * TD-336: usePluginStore 测试 — 覆盖 spec-134 乐观更新回滚逻辑
 * 重点测试 togglePlugin/uninstallPlugin 的快照→乐观set→try→catch回滚模式
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { usePluginStore } from '@/stores/usePluginStore';
import type { PluginItem } from '@/api/plugins';

// Mock plugins API
vi.mock('@/api/plugins', () => ({
  fetchPlugins: vi.fn(),
  togglePlugin: vi.fn(),
  uninstallPlugin: vi.fn(),
}));

// 导入 mock 后的 api 以便控制
import {
  fetchPlugins as fetchPluginsApi,
  togglePlugin as togglePluginApi,
  uninstallPlugin as uninstallPluginApi,
} from '@/api/plugins';

const makePlugin = (id: number, overrides: Partial<PluginItem> = {}): PluginItem => ({
  id,
  name: `Plugin ${id}`,
  description: `Description ${id}`,
  version: '1.0.0',
  author: 'test',
  manifest: {},
  is_active: false,
  is_installed: true,
  installed_at: null,
  checksum: 'abc',
  created_at: null,
  updated_at: null,
  sandbox_status: null,
  sandbox_pid: null,
  ...overrides,
});

beforeEach(() => {
  usePluginStore.setState({
    plugins: [],
    installedCount: 0,
  });
  vi.clearAllMocks();
});

describe('usePluginStore', () => {
  describe('初始状态', () => {
    it('plugins 应为空数组', () => {
      const state = usePluginStore.getState();
      expect(state.plugins).toEqual([]);
    });

    it('installedCount 应为 0', () => {
      const state = usePluginStore.getState();
      expect(state.installedCount).toBe(0);
    });
  });

  describe('fetchPlugins', () => {
    it('成功时应更新 plugins 和 installedCount', async () => {
      const mockPlugins = [
        makePlugin(1, { is_installed: true }),
        makePlugin(2, { is_installed: false }),
        makePlugin(3, { is_installed: true }),
      ];
      vi.mocked(fetchPluginsApi).mockResolvedValue(mockPlugins);

      const { fetchPlugins } = usePluginStore.getState();
      await fetchPlugins();

      const state = usePluginStore.getState();
      expect(state.plugins).toHaveLength(3);
      expect(state.installedCount).toBe(2);
    });

    it('API 失败时应保留本地状态', async () => {
      const existing = [makePlugin(1, { is_installed: true })];
      usePluginStore.setState({ plugins: existing, installedCount: 1 });
      vi.mocked(fetchPluginsApi).mockRejectedValue(new Error('Network error'));

      const { fetchPlugins } = usePluginStore.getState();
      await fetchPlugins();

      const state = usePluginStore.getState();
      expect(state.plugins).toEqual(existing);
      expect(state.installedCount).toBe(1);
    });
  });

  describe('togglePlugin (spec-134 乐观更新回滚)', () => {
    it('API 成功时应保留乐观更新结果', async () => {
      const plugins = [makePlugin(1, { is_active: false }), makePlugin(2, { is_active: true })];
      usePluginStore.setState({ plugins, installedCount: 2 });
      vi.mocked(togglePluginApi).mockResolvedValue({} as never);

      const { togglePlugin } = usePluginStore.getState();
      await togglePlugin(1);

      const state = usePluginStore.getState();
      expect(state.plugins[0].is_active).toBe(true);
      expect(state.plugins[1].is_active).toBe(true); // 未受影响
    });

    it('API 失败时应回滚到原状态', async () => {
      const plugins = [makePlugin(1, { is_active: false }), makePlugin(2, { is_active: true })];
      usePluginStore.setState({ plugins, installedCount: 2 });
      vi.mocked(togglePluginApi).mockRejectedValue(new Error('Server error'));

      const { togglePlugin } = usePluginStore.getState();
      await togglePlugin(1);

      const state = usePluginStore.getState();
      expect(state.plugins[0].is_active).toBe(false); // 回滚到原状态
      expect(state.plugins[1].is_active).toBe(true);
    });

    it('乐观更新应在 await 之前生效 (同步阶段)', async () => {
      const plugins = [makePlugin(1, { is_active: false })];
      usePluginStore.setState({ plugins, installedCount: 1 });
      vi.mocked(togglePluginApi).mockImplementation(async () => {
        // API 调用时, store 已乐观更新
        const state = usePluginStore.getState();
        expect(state.plugins[0].is_active).toBe(true);
        return {} as never;
      });

      const { togglePlugin } = usePluginStore.getState();
      await togglePlugin(1);
    });
  });

  describe('uninstallPlugin (spec-134 乐观更新回滚)', () => {
    it('API 成功时应从列表移除并更新 installedCount', async () => {
      const plugins = [makePlugin(1, { is_installed: true }), makePlugin(2, { is_installed: true })];
      usePluginStore.setState({ plugins, installedCount: 2 });
      vi.mocked(uninstallPluginApi).mockResolvedValue(undefined);

      const { uninstallPlugin } = usePluginStore.getState();
      await uninstallPlugin(1);

      const state = usePluginStore.getState();
      expect(state.plugins).toHaveLength(1);
      expect(state.plugins[0].id).toBe(2);
      expect(state.installedCount).toBe(1);
    });

    it('API 失败时应回滚到原状态', async () => {
      const plugins = [makePlugin(1, { is_installed: true }), makePlugin(2, { is_installed: true })];
      usePluginStore.setState({ plugins, installedCount: 2 });
      vi.mocked(uninstallPluginApi).mockRejectedValue(new Error('Server error'));

      const { uninstallPlugin } = usePluginStore.getState();
      await uninstallPlugin(1);

      const state = usePluginStore.getState();
      expect(state.plugins).toHaveLength(2); // 回滚
      expect(state.installedCount).toBe(2); // 回滚
    });

    it('卸载未安装插件时 installedCount 不变', async () => {
      const plugins = [
        makePlugin(1, { is_installed: false }), // 未安装
        makePlugin(2, { is_installed: true }),
      ];
      usePluginStore.setState({ plugins, installedCount: 1 });
      vi.mocked(uninstallPluginApi).mockResolvedValue(undefined);

      const { uninstallPlugin } = usePluginStore.getState();
      await uninstallPlugin(1);

      const state = usePluginStore.getState();
      expect(state.plugins).toHaveLength(1); // 仍移除
      expect(state.installedCount).toBe(1); // 未变 (本来就只有 1 个 installed)
    });

    it('乐观更新应在 await 之前生效 (同步阶段)', async () => {
      const plugins = [makePlugin(1, { is_installed: true })];
      usePluginStore.setState({ plugins, installedCount: 1 });
      vi.mocked(uninstallPluginApi).mockImplementation(async () => {
        const state = usePluginStore.getState();
        expect(state.plugins).toHaveLength(0); // 已乐观移除
        return undefined;
      });

      const { uninstallPlugin } = usePluginStore.getState();
      await uninstallPlugin(1);
    });
  });
});
