/**
 * plugin status management Store
 * management plugin list, already install count, enable / disable / unmount etc. operation
 */
import { create } from 'zustand';
import {
  fetchPlugins as fetchPluginsApi,
  togglePlugin as togglePluginApi,
  uninstallPlugin as uninstallPluginApi,
} from '@/api/plugins';
import type { PluginItem } from '@/api/plugins';

/** plugin Store status API */
interface PluginState {
  plugins: PluginItem[];
  installedCount: number;
  /** get plugin list */
  fetchPlugins: () => Promise<void>;
  /** switch plugin enable / disable status */
  togglePlugin: (id: string | number) => Promise<void>;
  /** uninstall plugin */
  uninstallPlugin: (id: string | number) => Promise<void>;
}

/** plugin status management */
export const usePluginStore = create<PluginState>((set) => ({
  plugins: [],
  installedCount: 0,

  /** get plugin list, sync update installedCount */
  fetchPlugins: async () => {
    try {
      const plugins = await fetchPluginsApi();
      set({
        plugins,
        installedCount: plugins.filter((p) => p.is_installed).length,
      });
    } catch {
      // preserve local state when service unavailable
    }
  },

  /** TD-335 spec-134: switch plugin enable/disable — 乐观更新 + 失败回滚
   *  原: try API → catch 空忽略 → 无论成功失败都 set (UI 显示已切换但服务器未变)
   *  新: 快照旧状态 → 乐观 set → try API → catch 回滚 */
  togglePlugin: async (id: string | number) => {
    const prevPlugins = usePluginStore.getState().plugins;
    set((state) => {
      const plugins = state.plugins.map((p) => (p.id === id ? { ...p, is_active: !p.is_active } : p));
      return { plugins };
    });
    try {
      await togglePluginApi(Number(id));
    } catch {
      set({ plugins: prevPlugins });
    }
  },

  /** TD-335 spec-134: uninstall plugin — 乐观更新 + 失败回滚
   *  原: try API → catch 空忽略 → 无论成功失败都 set (UI 显示已卸载但服务器未变)
   *  新: 快照旧状态 → 乐观 set → try API → catch 回滚 */
  uninstallPlugin: async (id: string | number) => {
    const prevPlugins = usePluginStore.getState().plugins;
    const prevCount = usePluginStore.getState().installedCount;
    set((state) => {
      const plugins = state.plugins.filter((p) => p.id !== id);
      return {
        plugins,
        installedCount: plugins.filter((p) => p.is_installed).length,
      };
    });
    try {
      await uninstallPluginApi(Number(id));
    } catch {
      set({ plugins: prevPlugins, installedCount: prevCount });
    }
  },
}));
