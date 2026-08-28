/**
 * Cron expression editor component
 * provides Cron expression input and visual configuration
 */
import { useState, useCallback } from 'react';
import { Input, Space, Tag, theme as antTheme } from 'antd';

/** CronExpressionEditor component props */
interface CronExpressionEditorProps {
  value?: string;
  onChange?: (cron: string) => void;
  disabled?: boolean;
}

/** Cron quick presets */
const CRON_PRESETS: { label: string; value: string }[] = [
  { label: '每分钟', value: '* * * * *' },
  { label: '每5分钟', value: '*/5 * * * *' },
  { label: '每30分钟', value: '*/30 * * * *' },
  { label: '每小时', value: '0 * * * *' },
  { label: '每天午夜', value: '0 0 * * *' },
  { label: '每周一午夜', value: '0 0 * * 1' },
  { label: '每月1号午夜', value: '0 0 1 * *' },
];

/**
 * Cron expression visual editor
 * supports manual input and preset selection
 */
export function CronExpressionEditor({ value = '* * * * *', onChange, disabled = false }: CronExpressionEditorProps) {
  const { token } = antTheme.useToken();
  const [cronParts, setCronParts] = useState<string[]>(value.split(' '));

  /** update a specific Cron field */
  const updatePart = useCallback(
    (index: number, val: string) => {
      const newParts = [...cronParts];
      newParts[index] = val;
      setCronParts(newParts);
      onChange?.(newParts.join(' '));
    },
    [cronParts, onChange],
  );

  /** use preset Cron */
  const applyPreset = useCallback(
    (preset: string) => {
      const parts = preset.split(' ');
      setCronParts(parts);
      onChange?.(preset);
    },
    [onChange],
  );

  const labels = ['分钟', '小时', '日', '月', '星期'];

  return (
    <Space orientation="vertical" className="gaf-w-full">
      <div className="gaf-gap-xs gaf-w-full" style={{ display: 'flex' }}>
        {cronParts.map((part, idx) => (
          <div key={`part-${labels[idx]}`} className="gaf-flex-1" style={{ display: 'flex', flexDirection: 'column' }}>
            <span className="gaf-text-xxs" style={{ color: token.colorTextTertiary, marginBottom: 2 }}>
              {labels[idx]}
            </span>
            <Input
              value={part}
              onChange={(e) => updatePart(idx, e.target.value)}
              disabled={disabled}
              className="gaf-w-full"
            />
          </div>
        ))}
      </div>
      <Space wrap>
        <span style={{ color: token.colorTextTertiary }}>快捷选择：</span>
        {CRON_PRESETS.map((preset) => (
          <Tag
            key={preset.value}
            color={value === preset.value ? 'blue' : 'default'}
            style={{ cursor: 'pointer' }}
            onClick={() => applyPreset(preset.value)}
          >
            {preset.label}
          </Tag>
        ))}
      </Space>
      <div className="gaf-text-xs" style={{ color: token.colorTextSecondary }}>
        当前表达式：
        <code style={{ background: token.colorBgLayout, padding: '2px 6px', borderRadius: 3 }}>
          {cronParts.join(' ')}
        </code>
      </div>
    </Space>
  );
}

export default CronExpressionEditor;
