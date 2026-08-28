/**
 * language switch component
 * dropdown select language, switch global locale and trigger subscribe component re-render
 */
import { useState, useEffect, useMemo } from 'react';
import { Select } from 'antd';
import { GlobalOutlined } from '@ant-design/icons';
import { getLocale, setLocale, subscribeLocale, useTranslation } from './index';
import type { SupportedLocale } from './index';

/** language switch dropdown selector */
export default function LanguageSwitcher() {
  const [locale, setLocaleState] = useState(getLocale());
  const t = useTranslation();

  useEffect(() => subscribeLocale(() => setLocaleState(getLocale())), []);

  const langOptions: { value: SupportedLocale; label: string }[] = useMemo(
    () => [
      { value: 'system', label: t('app.follow_system') },
      { value: 'zh-CN', label: '中文' },
      { value: 'en-US', label: 'English' },
      { value: 'ja-JP', label: '日本語' },
      { value: 'ko-KR', label: '한국어' },
    ],
    [t],
  );

  return (
    <Select
      value={locale}
      onChange={(val) => setLocale(val)}
      options={langOptions}
      size="small"
      style={{ minWidth: 110 }}
      prefix={<GlobalOutlined />}
    />
  );
}
