/**
 * DPI scaling selector component
 * supports Auto / 1× / 1.25× / 1.5× / 1.75× / 2×
 * scaling settings persisted to localStorage, applied to root container via CSS transform: scale()
 */
import { useEffect, useState } from 'react';
import { Dropdown, Button } from 'antd';
import { FontSizeOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';

/** DPI scaling level type */
export type DpiScale = 'auto' | '1' | '1.25' | '1.5' | '1.75' | '2';

/** scaling level config */
const dpiOptions: { key: DpiScale; label: string; value: number | null }[] = [
  { key: 'auto', label: 'Auto', value: null },
  { key: '1', label: '100% (1×)', value: 1 },
  { key: '1.25', label: '125% (1.25×)', value: 1.25 },
  { key: '1.5', label: '150% (1.5×)', value: 1.5 },
  { key: '1.75', label: '175% (1.75×)', value: 1.75 },
  { key: '2', label: '200% (2×)', value: 2 },
];

/** DPI storage key */
const DPI_STORAGE_KEY = 'gaf_dpi_scale';

/**
 * get saved DPI scaling level from localStorage
 * default returns 'auto'
 */
function getStoredDpi(): DpiScale {
  const stored = localStorage.getItem(DPI_STORAGE_KEY);
  if (stored && dpiOptions.some((o) => o.key === stored)) {
    return stored as DpiScale;
  }
  return 'auto';
}

/**
 * persist DPI scaling level to localStorage
 */
function setStoredDpi(scale: DpiScale): void {
  localStorage.setItem(DPI_STORAGE_KEY, scale);
}

/**
 * compute actual scale value based on DPI scaling level
 * returns null in auto mode (use default scaling)
 */
function resolveDpiScale(scale: DpiScale): number | null {
  if (scale === 'auto') return null;
  const opt = dpiOptions.find((o) => o.key === scale);
  return opt?.value ?? null;
}

interface DpiScalerProps {
  onChange?: (scale: DpiScale) => void;
}

/**
 * DPI scaling dropdown selector
 * modify CSS transform of body or root container to apply scaling
 */
export function DpiScaler({ onChange }: DpiScalerProps) {
  const [scale, setScale] = useState<DpiScale>(getStoredDpi);

  /** apply scaling to root container */
  useEffect(() => {
    const value = resolveDpiScale(scale);
    const root = document.getElementById('root');
    if (!root) return;

    if (value === null) {
      root.style.transform = '';
      root.style.transformOrigin = '';
    } else {
      root.style.transform = `scale(${value})`;
      root.style.transformOrigin = 'top left';
    }
  }, [scale]);

  /** switch scaling handler */
  const handleDpiChange = (key: DpiScale) => {
    setScale(key);
    setStoredDpi(key);
    onChange?.(key);
  };

  /** dropdown menu item config */
  const menuItems: MenuProps['items'] = dpiOptions.map((opt) => ({
    key: opt.key,
    label: opt.label,
    onClick: () => handleDpiChange(opt.key),
  }));

  const currentLabel = dpiOptions.find((o) => o.key === scale)?.label || 'Auto';

  return (
    <Dropdown
      menu={{ items: menuItems, selectable: true, selectedKeys: [scale] }}
      placement="bottomRight"
      trigger={['click']}
    >
      <Button
        type="text"
        icon={<FontSizeOutlined />}
        title={`DPI 缩放: ${currentLabel}`}
        className="gaf-text-md"
        style={{ width: 36, height: 36 }}
      />
    </Dropdown>
  );
}

export default DpiScaler;
