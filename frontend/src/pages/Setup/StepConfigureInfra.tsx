import React, { useEffect, useState } from 'react';
import { Badge, Button, Card, Spin, Modal, theme, message as antMessage } from 'antd';
import { ReloadOutlined, BugOutlined } from '@ant-design/icons';
import { getSystemHealth } from '@/api/init';
import EnvDiagnosisPanel from './EnvDiagnosisPanel';
import { useTranslation } from '@/i18n';

interface HealthItem {
  name: string;
  label: string;
  status: 'pass' | 'warning' | 'fail';
  message: string;
}

interface StepConfigureInfraProps {
  onNext: () => void;
}

/** Map health status to Badge status type */
const STATUS_BADGE: Record<string, 'success' | 'warning' | 'error'> = {
  pass: 'success',
  warning: 'warning',
  fail: 'error',
};

/** Map health status to i18n key */
const STATUS_TEXT_KEYS: Record<string, string> = {
  pass: 'setup.infra.status_pass',
  warning: 'setup.infra.status_warning',
  fail: 'setup.infra.status_fail',
};

/**
 * Step 2: Infrastructure configuration
 * Auto-detect database/Redis/Celery/WebSocket connection status
 * Support re-check and environment diagnosis
 */
const StepConfigureInfra: React.FC<StepConfigureInfraProps> = ({ onNext }) => {
  const t = useTranslation();
  const { token } = theme.useToken();
  const [healthItems, setHealthItems] = useState<HealthItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [diagnosisVisible, setDiagnosisVisible] = useState(false);

  /** Fetch system health status from API */
  const fetchHealth = async () => {
    setLoading(true);
    try {
      const data = await getSystemHealth();
      setHealthItems([
        { name: 'db', label: t('setup.infra.label_db'), status: data.db, message: data.db_message || '' },
        { name: 'redis', label: 'Redis', status: data.redis, message: data.redis_message || '' },
        { name: 'celery', label: 'Celery', status: data.celery, message: data.celery_message || '' },
        { name: 'ws', label: 'WebSocket', status: data.ws, message: data.ws_message || '' },
        { name: 'disk', label: t('setup.infra.label_disk'), status: data.disk, message: data.disk_message || '' },
        {
          name: 'memory',
          label: t('setup.infra.label_memory'),
          status: data.memory,
          message: data.memory_message || '',
        },
      ]);
    } catch {
      antMessage.error('Failed to load infrastructure config');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  const hasFailure = healthItems.some((item) => item.status === 'fail');

  return (
    <div>
      {loading ? (
        <div className="gaf-text-center" style={{ padding: 40 }}>
          <Spin description={t('setup.infra.spin_checking')} />
        </div>
      ) : (
        <>
          <div>
            {healthItems.map((item) => {
              const badgeStatus = STATUS_BADGE[item.status];
              const statusText = t(STATUS_TEXT_KEYS[item.status]);
              return (
                <div
                  key={item.name}
                  className="gaf-flex-between gaf-py-md gaf-px-lg"
                  style={{ borderBottom: `1px solid ${token.colorBorderSecondary}` }}
                >
                  <div className="gaf-flex-1" style={{ minWidth: 0 }}>
                    <div className="gaf-font-medium">{item.label}</div>
                    <div className="gaf-text-13" style={{ color: token.colorTextSecondary }}>
                      {item.message || statusText}
                    </div>
                  </div>
                  <Badge status={badgeStatus} text={statusText} />
                </div>
              );
            })}
          </div>
          <div className="gaf-flex-between gaf-mt-lg">
            <Button icon={<ReloadOutlined />} onClick={fetchHealth}>
              {t('setup.infra.btn_recheck')}
            </Button>
            <Button icon={<BugOutlined />} onClick={() => setDiagnosisVisible(true)}>
              {t('setup.infra.btn_check_env')}
            </Button>
          </div>
        </>
      )}
      <Card size="small" className="gaf-mt-lg" style={{ background: token.colorBgLayout }}>
        <strong>{t('setup.infra.card_title')}</strong>
        <p className="gaf-m-0">{t('setup.infra.card_desc')}</p>
      </Card>
      {hasFailure && (
        <Card
          size="small"
          className="gaf-mt-md"
          style={{ background: token.colorErrorBg, border: `1px solid ${token.colorErrorBorder}` }}
        >
          {t('setup.infra.alert_failure')}
        </Card>
      )}
      <Modal
        title={t('setup.infra.modal_env_diagnosis')}
        open={diagnosisVisible}
        onCancel={() => setDiagnosisVisible(false)}
        footer={null}
        width={560}
      >
        <EnvDiagnosisPanel />
      </Modal>
      <Button type="primary" onClick={onNext} className="gaf-mt-xl" block size="large">
        {t('setup.btn_next')}
      </Button>
    </div>
  );
};

export default StepConfigureInfra;
