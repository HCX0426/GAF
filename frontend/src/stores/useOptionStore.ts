/**
 * option config status management Store
 * supports 4 level priority combine and ( default value < system config < user config < temp when override )
 */
import { create } from 'zustand';
import { fetchAppSettings } from '@/api/misc';

/** option Store status API */
interface OptionState {
  /** combine and after option (4 level priority ) */
  options: Record<string, unknown>;
  /** get and combine and has tier option */
  fetchOptions: () => Promise<void>;
  /** settings single option ( temp when override layer ) */
  setOption: (key: string, value: unknown) => void;
  /** reset option to system default value */
  resetOptions: () => void;
}

/** default option value */
const DEFAULT_OPTIONS: Record<string, unknown> = {
  theme: 'light',
  language: 'zh-CN',
  refreshInterval: 30,
  pageSize: 20,
};

/** option config status management */
export const useOptionStore = create<OptionState>((set) => ({
  options: { ...DEFAULT_OPTIONS },

  /** get and combine and 4 level priority option */
  fetchOptions: async () => {
    try {
      const data = await fetchAppSettings<Record<string, unknown>[]>();
      const systemConfig: Record<string, unknown> = {};
      if (Array.isArray(data)) {
        for (const item of data) {
          if (item && typeof item === 'object' && 'key' in item && 'value' in item) {
            systemConfig[item.key as string] = item.value;
          }
        }
      }
      set((state) => ({
        options: { ...DEFAULT_OPTIONS, ...systemConfig, ...state.options },
      }));
    } catch {
      // service unavailable when use default value + local status
    }
  },

  /** settings single option value ( temp when override layer level ) */
  setOption: (key: string, value: unknown) => {
    set((state) => ({
      options: { ...state.options, [key]: value },
    }));
  },

  /** reset option is system default value */
  resetOptions: () => {
    set({ options: { ...DEFAULT_OPTIONS } });
  },
}));
