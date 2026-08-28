/**
 * theme switch component
 * supports light / dark / follow system three modes switch
 */
import { useEffect, useState } from 'react';
import { Dropdown, Button } from 'antd';
import { SunOutlined, MoonOutlined, DesktopOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { getStoredTheme, setStoredTheme, getThemeClass, resolveTheme, notifyThemeChange } from './index';
import type { ThemeMode } from './index';

/** theme mode to corresponding icon and label */
const themeOptions: { key: ThemeMode; icon: React.ReactNode; label: string }[] = [
  { key: 'system', icon: <DesktopOutlined />, label: '跟随系统' },
  { key: 'light', icon: <SunOutlined />, label: '亮色模式' },
  { key: 'dark', icon: <MoonOutlined />, label: '暗色模式' },
];

/** current theme icon mapping */
const modeIcons: Record<string, React.ReactNode> = {
  light: <SunOutlined />,
  dark: <MoonOutlined />,
  system: <DesktopOutlined />,
};

interface ThemeSwitcherProps {
  onChange?: (mode: ThemeMode) => void;
}

/** theme switch dropdown button component */
export default function ThemeSwitcher({ onChange }: ThemeSwitcherProps) {
  const [mode, setMode] = useState<ThemeMode>(getStoredTheme);

  /** listen system theme change (system mode below ) */
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    /** system theme change more when, if current is system mode then notify refresh */
    const handler = () => {
      if (getStoredTheme() === 'system') {
        onChange?.('system');
      }
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [onChange]);

  /** switch theme handle */
  const handleThemeChange = (key: ThemeMode) => {
    setMode(key);
    setStoredTheme(key);
    /** update body above theme class */
    document.body.classList.remove('theme-light', 'theme-dark');
    document.body.classList.add(getThemeClass(key));
    notifyThemeChange(key);
    onChange?.(key);
  };

  /** initial start transform when settings body class */
  useEffect(() => {
    document.body.classList.remove('theme-light', 'theme-dark');
    document.body.classList.add(getThemeClass(mode));
  }, []);

  /** dropdown menu item config */
  const menuItems: MenuProps['items'] = themeOptions.map((opt) => ({
    key: opt.key,
    icon: opt.icon,
    label: opt.label,
    onClick: () => handleThemeChange(opt.key),
  }));

  const resolved = resolveTheme(mode);

  return (
    <Dropdown
      menu={{ items: menuItems, selectable: true, selectedKeys: [mode] }}
      placement="bottomRight"
      trigger={['click']}
    >
      <Button
        type="text"
        icon={modeIcons[resolved]}
        title={`当前主题: ${themeOptions.find((o) => o.key === mode)?.label}`}
        className="gaf-text-md"
        style={{ width: 36, height: 36 }}
      />
    </Dropdown>
  );
}
