/**
 * theme config system
 * supports light / dark / follow system three modes
 * based on antd ConfigProvider theme token
 */
import { theme } from 'antd';

/** theme mode */
export type ThemeMode = 'light' | 'dark' | 'system';

/** theme storage key */
const THEME_STORAGE_KEY = 'gaf_theme_mode';

/** light theme token override */
export const lightThemeTokens = {
  colorPrimary: '#1677ff',
  colorBgBase: '#f5f5f5',
  colorBgContainer: '#ffffff',
  colorBgElevated: '#ffffff',
  colorBgLayout: '#f0f2f5',
  colorText: 'rgba(0, 0, 0, 0.88)',
  colorTextSecondary: 'rgba(0, 0, 0, 0.65)',
  colorTextTertiary: 'rgba(0, 0, 0, 0.45)',
  colorFillAlter: 'rgba(0, 0, 0, 0.02)',
  colorFillContent: 'rgba(0, 0, 0, 0.06)',
  colorBorder: 'rgba(0, 0, 0, 0.06)',
  colorBorderSecondary: 'rgba(0, 0, 0, 0.04)',
  colorLink: '#1677ff',
  colorSuccess: '#52c41a',
  colorWarning: '#faad14',
  colorError: '#ff4d4f',
  borderRadius: 8,
  borderRadiusLG: 12,
};

/**
 * from localStorage get already save theme mode
 * default returns 'system'( follow system )
 */
export function getStoredTheme(): ThemeMode {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  if (stored === 'dark' || stored === 'light' || stored === 'system') {
    return stored;
  }
  return 'system';
}

/**
 * persistence theme mode to localStorage
 */
export function setStoredTheme(mode: ThemeMode): void {
  localStorage.setItem(THEME_STORAGE_KEY, mode);
}

/**
 * based on theme mode and system preference calculates actual theme
 * system mode below based on matchMedia judge
 */
export function resolveTheme(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') {
    if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }
  return mode;
}

/** theme change more subscribe */
let themeListeners: Array<(mode: ThemeMode) => void> = [];

/**
 * subscribe theme change more, return cancel subscribe function
 */
export function subscribeTheme(listener: (mode: ThemeMode) => void): () => void {
  themeListeners.push(listener);
  return () => {
    themeListeners = themeListeners.filter((l) => l !== listener);
  };
}

/**
 * notify has subscribe subscriber theme already change more
 */
export function notifyThemeChange(mode: ThemeMode): void {
  themeListeners.forEach((fn) => fn(mode));
}

/**
 * get antd theme algorithm
 */
export function getThemeAlgorithm(mode: ThemeMode) {
  const resolved = resolveTheme(mode);
  return resolved === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm;
}

/**
 * get theme to corresponding CSS class
 */
export function getThemeClass(mode: ThemeMode): string {
  const resolved = resolveTheme(mode);
  return resolved === 'dark' ? 'theme-dark' : 'theme-light';
}

/**
 * get complete antd theme config
 */
export function getAntdThemeConfig(mode: ThemeMode) {
  const resolved = resolveTheme(mode);
  const algorithm = resolved === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm;
  const tokens = resolved === 'dark' ? darkThemeTokens : lightThemeTokens;

  return {
    algorithm,
    token: tokens,
  };
}

/** dark theme token override */
export const darkThemeTokens = {
  colorPrimary: '#1677ff',
  colorBgBase: '#0a0a0a',
  colorBgContainer: '#141414',
  colorBgElevated: '#1f1f1f',
  colorBgLayout: '#0a0a0a',
  colorText: 'rgba(255, 255, 255, 0.88)',
  colorTextSecondary: 'rgba(255, 255, 255, 0.65)',
  colorTextTertiary: 'rgba(255, 255, 255, 0.45)',
  colorFillAlter: 'rgba(255, 255, 255, 0.04)',
  colorFillContent: 'rgba(255, 255, 255, 0.08)',
  colorBorder: 'rgba(255, 255, 255, 0.08)',
  colorBorderSecondary: 'rgba(255, 255, 255, 0.05)',
  colorLink: '#1677ff',
  colorSuccess: '#52c41a',
  colorWarning: '#faad14',
  colorError: '#ff4d4f',
  borderRadius: 8,
  borderRadiusLG: 12,
};
