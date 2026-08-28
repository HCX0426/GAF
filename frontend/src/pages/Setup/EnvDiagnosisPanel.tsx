import React, { useEffect, useState } from 'react';
import { Badge, Alert, Spin, Tag, theme as antTheme } from 'antd';
import { getEnvCheck } from '@/api/init';
import { useTranslation } from '@/i18n';

interface EnvCheckItem {
  name: string;
  label: string;
  current_version: string;
  required_version: string;
  status: 'pass' | 'fail' | 'warning';
  suggestion?: string | null;
}

/** Map status string to Badge status type */
const STATUS_BADGE: Record<string, 'success' | 'warning' | 'error'> = {
  pass: 'success',
  warning: 'warning',
  fail: 'error',
};

/** Map status string to Tag color */
const STATUS_COLOR: Record<string, string> = {
  pass: 'green',
  warning: 'orange',
  fail: 'red',
};

/** Map status string to i18n key */
const STATUS_LABEL_KEYS: Record<string, string> = {
  pass: 'setup.env.status_pass',
  warning: 'setup.env.status_warning',
  fail: 'setup.env.status_fail',
};

/**
 * Environment diagnosis panel
 * Detects Python/Node.js/ADB/PostgreSQL/Redis version compatibility
 * Displayed in a Modal, accessible from any wizard step
 */
const EnvDiagnosisPanel: React.FC = () => {
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const [items, setItems] = useState<EnvCheckItem[]>([]);
  const [loading, setLoading] = useState(true);

  /** Load environment check results and map to display items */
  useEffect(() => {
    getEnvCheck()
      .then((data) => {
        setItems([
          { name: 'python', label: 'Python', ...data.python },
          { name: 'node', label: 'Node.js', ...data.node },
          { name: 'adb', label: 'ADB', ...data.adb },
          { name: 'postgresql', label: 'PostgreSQL', ...data.postgresql },
          { name: 'redis', label: 'Redis', ...data.redis },
          { name: 'disk', label: t('setup.env.label_disk'), ...data.disk },
        ]);
      })
      .finally(() => setLoading(false));
  }, [t]);

  if (loading) return <Spin description={t('setup.env.spin_diagnosing')} />;

  return (
    <div>
      {items.map((item) => {
        const badgeStatus = STATUS_BADGE[item.status];
        const color = STATUS_COLOR[item.status];
        const label = t(STATUS_LABEL_KEYS[item.status]);
        return (
          <div
            key={item.name}
            className="gaf-flex gaf-py-md gaf-px-lg"
            style={{ alignItems: 'flex-start', borderBottom: `1px solid ${token.colorBorderSecondary}` }}
          >
            <div className="gaf-flex-1" style={{ minWidth: 0 }}>
              <div className="gaf-font-medium">
                {item.label}
                <Tag color={color} className="gaf-ml-sm">
                  {item.current_version}
                </Tag>
              </div>
              <div className="gaf-mt-xs gaf-text-13" style={{ color: token.colorTextSecondary }}>
                {item.status === 'fail' && item.suggestion ? (
                  <Alert type="error" description={item.suggestion} className="gaf-mt-xs" />
                ) : (
                  t('setup.env.required_version', { version: item.required_version })
                )}
              </div>
            </div>
            <Badge status={badgeStatus} text={label} />
          </div>
        );
      })}
    </div>
  );
};

export default EnvDiagnosisPanel;
