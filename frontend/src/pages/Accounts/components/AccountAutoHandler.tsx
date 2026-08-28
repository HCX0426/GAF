/**
 * exception handle config component
 * control account exception when auto handle row is, config persistence to localStorage
 */
import { useState, useEffect } from 'react';
import { Card, Switch, Space, Typography } from 'antd';
import { useTranslation } from '@/i18n';

const { Text } = Typography;

/** localStorage storage key */
const STORAGE_KEY = 'account_auto_handler_config';

/** config API */
interface AutoHandlerConfig {
  autoRemove: boolean;
  inAppNotify: boolean;
  trayNotify: boolean;
}

/**
 * load persistence config
 */
function loadConfig(): AutoHandlerConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return JSON.parse(raw);
    }
  } catch {
    // parse fail then use default value
  }
  return { autoRemove: true, inAppNotify: true, trayNotify: false };
}

/**
 * save config to localStorage
 */
function saveConfig(config: AutoHandlerConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

/**
 * account exception auto handle config panel
 */
export function AccountAutoHandler() {
  const t = useTranslation();
  const [config, setConfig] = useState<AutoHandlerConfig>(loadConfig);

  /** component mount when from localStorage read fetch */
  useEffect(() => {
    setConfig(loadConfig());
  }, []);

  /**
   * update config item and persistence
   */
  const updateConfig = (key: keyof AutoHandlerConfig, value: boolean) => {
    const next = { ...config, [key]: value };
    setConfig(next);
    saveConfig(next);
  };

  return (
    <Card size="small" title={t('accounts.auto_handler_title')}>
      <Space orientation="vertical" className="gaf-w-full">
        <div className="gaf-flex-between">
          <Text>{t('accounts.auto_remove')}</Text>
          <Switch checked={config.autoRemove} onChange={(v) => updateConfig('autoRemove', v)} />
        </div>

        <div className="gaf-flex-between">
          <Text>{t('accounts.in_app_notify')}</Text>
          <Switch checked={config.inAppNotify} onChange={(v) => updateConfig('inAppNotify', v)} />
        </div>

        <div className="gaf-flex-between">
          <Text>{t('accounts.tray_notify')}</Text>
          <Switch checked={config.trayNotify} onChange={(v) => updateConfig('trayNotify', v)} />
        </div>
      </Space>
    </Card>
  );
}

export default AccountAutoHandler;
