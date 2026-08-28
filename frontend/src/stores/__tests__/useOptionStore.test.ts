/**
 * TD-336 #4: useOptionStore 测试 — 覆盖 4 级优先级配置合并 + 设置/重置
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useOptionStore } from '@/stores/useOptionStore';

// Mock misc API
vi.mock('@/api/misc', () => ({
  fetchAppSettings: vi.fn(),
}));

import { fetchAppSettings } from '@/api/misc';

beforeEach(() => {
  useOptionStore.setState({ options: { theme: 'light', language: 'zh-CN', refreshInterval: 30, pageSize: 20 } });
  vi.clearAllMocks();
});

describe('useOptionStore', () => {
  describe('初始状态', () => {
    it('应包含默认配置 (theme/language/refreshInterval/pageSize)', () => {
      const { options } = useOptionStore.getState();
      expect(options.theme).toBe('light');
      expect(options.language).toBe('zh-CN');
      expect(options.refreshInterval).toBe(30);
      expect(options.pageSize).toBe(20);
    });
  });

  describe('fetchOptions', () => {
    it('成功时应合并系统配置 (本地优先级高于系统配置)', async () => {
      // 合并优先级: DEFAULT_OPTIONS < systemConfig < state.options (本地)
      vi.mocked(fetchAppSettings).mockResolvedValue([
        { key: 'theme', value: 'dark' }, // 系统配置
        { key: 'customSysKey', value: 'sysVal' }, // 系统独有 key (本地无)
      ] as never);

      const { fetchOptions } = useOptionStore.getState();
      await fetchOptions();

      const { options } = useOptionStore.getState();
      // 本地 theme='light' 优先级高于系统 theme='dark'
      expect(options.theme).toBe('light');
      // 系统独有 key 应被合并进来
      expect(options.customSysKey).toBe('sysVal');
      // 默认未覆盖的 key 保留
      expect(options.language).toBe('zh-CN');
    });

    it('API 失败时应保留本地配置不抛错', async () => {
      vi.mocked(fetchAppSettings).mockRejectedValue(new Error('Network error'));

      const { fetchOptions } = useOptionStore.getState();
      await fetchOptions(); // 不应 throw

      const { options } = useOptionStore.getState();
      expect(options.theme).toBe('light'); // 保留原配置
    });

    it('返回非数组时应安全跳过合并', async () => {
      vi.mocked(fetchAppSettings).mockResolvedValue({ not: 'array' } as never);

      const { fetchOptions } = useOptionStore.getState();
      await fetchOptions();

      const { options } = useOptionStore.getState();
      expect(options.theme).toBe('light'); // 默认保留
    });
  });

  describe('setOption', () => {
    it('应设置单个选项值 (临时覆盖层)', () => {
      const { setOption } = useOptionStore.getState();
      setOption('theme', 'dark');

      const { options } = useOptionStore.getState();
      expect(options.theme).toBe('dark');
      expect(options.pageSize).toBe(20); // 其他不变
    });

    it('应支持新增未定义的 key', () => {
      const { setOption } = useOptionStore.getState();
      setOption('customKey', 'customValue');

      const { options } = useOptionStore.getState();
      expect(options.customKey).toBe('customValue');
    });
  });

  describe('resetOptions', () => {
    it('应重置为系统默认值', () => {
      const { setOption, resetOptions } = useOptionStore.getState();
      setOption('theme', 'dark');
      setOption('pageSize', 100);
      expect(useOptionStore.getState().options.theme).toBe('dark');

      resetOptions();

      const { options } = useOptionStore.getState();
      expect(options.theme).toBe('light');
      expect(options.pageSize).toBe(20);
    });
  });
});
