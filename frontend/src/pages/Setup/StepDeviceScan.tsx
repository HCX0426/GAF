import React, { useEffect, useState, useMemo } from 'react';
import { Table, Badge, Button, Empty, Card, Spin, Tag, message as antMessage, theme } from 'antd';
import { ReloadOutlined, AndroidOutlined, WindowsOutlined } from '@ant-design/icons';
import { scanDevices } from '@/api/init';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/i18n';

interface ScannedDevice {
  id: string;
  name: string;
  type: 'emulator' | 'window';
  emulator_type?: string;
  status: 'online' | 'warning' | 'offline';
  adb_port?: number;
  resolution?: string;
}

/** Map emulator type to i18n key */
const EMULATOR_TYPE_KEYS: Record<string, string> = {
  mumu: 'setup.device.emulator_mumu',
  ldplayer: 'setup.device.emulator_ldplayer',
  bluestacks: 'setup.device.emulator_bluestacks',
  xiaoyao: 'setup.device.emulator_xiaoyao',
  yeshen: 'setup.device.emulator_yeshen',
};

/** Map device status to Badge status type */
const STATUS_BADGE: Record<string, 'success' | 'warning' | 'error'> = {
  online: 'success',
  warning: 'warning',
  offline: 'error',
};

/** Map device status to i18n key */
const STATUS_TEXT_KEYS: Record<string, string> = {
  online: 'setup.device.status_online',
  warning: 'setup.device.status_warning',
  offline: 'setup.device.status_offline',
};

interface StepDeviceScanProps {
  onNext: () => void;
}

/**
 * Step 3: detect local device
 * auto scan emulator (MuMu/ LDPlayer / BlueStacks / MEmu / Nox ) and Windows game window
 */
const StepDeviceScan: React.FC<StepDeviceScanProps> = ({ onNext }) => {
  const { token } = theme.useToken();
  const t = useTranslation();
  const [devices, setDevices] = useState<ScannedDevice[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchDevices = async () => {
    setLoading(true);
    try {
      const data = await scanDevices();
      setDevices(data as unknown as ScannedDevice[]);
    } catch {
      antMessage.error('Failed to scan devices');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDevices();
  }, []);

  const columns: ColumnsType<ScannedDevice> = useMemo(
    () => [
      { title: t('setup.device.col_name'), dataIndex: 'name', key: 'name' },
      {
        title: t('setup.device.col_type'),
        dataIndex: 'type',
        key: 'type',
        render: (type: string, record: ScannedDevice) => (
          <span>
            {type === 'emulator' ? <AndroidOutlined /> : <WindowsOutlined />}{' '}
            {type === 'emulator' ? t('setup.device.type_emulator') : t('setup.device.type_window')}
            {record.emulator_type && (
              <Tag className="gaf-ml-sm">
                {EMULATOR_TYPE_KEYS[record.emulator_type]
                  ? t(EMULATOR_TYPE_KEYS[record.emulator_type])
                  : record.emulator_type}
              </Tag>
            )}
          </span>
        ),
      },
      {
        title: t('setup.device.col_status'),
        dataIndex: 'status',
        key: 'status',
        render: (status: string) => {
          return <Badge status={STATUS_BADGE[status]} text={t(STATUS_TEXT_KEYS[status])} />;
        },
      },
      {
        title: t('setup.device.col_adb_port'),
        dataIndex: 'adb_port',
        key: 'adb_port',
        render: (port: number | undefined) => port || '—',
      },
      {
        title: t('setup.device.col_resolution'),
        dataIndex: 'resolution',
        key: 'resolution',
        render: (res: string | undefined) => res || '—',
      },
    ],
    [t],
  );

  return (
    <div>
      {loading ? (
        <div className="gaf-text-center" style={{ padding: 40 }}>
          <Spin description={t('setup.device.spin_scanning')} />
        </div>
      ) : devices.length === 0 ? (
        <Empty description={t('setup.device.empty_no_device')}>
          <Button icon={<ReloadOutlined />} onClick={fetchDevices}>
            {t('setup.device.btn_rescan')}
          </Button>
        </Empty>
      ) : (
        <>
          <Table dataSource={devices} columns={columns} rowKey="id" pagination={false} size="small" />
          <Button icon={<ReloadOutlined />} onClick={fetchDevices} className="gaf-mt-lg">
            {t('setup.device.btn_rescan')}
          </Button>
        </>
      )}
      <Card size="small" className="gaf-mt-lg" style={{ background: token.colorBgLayout }}>
        <strong>{t('setup.device.card_title')}</strong>
        <p className="gaf-m-0">{t('setup.device.card_desc')}</p>
      </Card>
      <Button type="primary" onClick={onNext} className="gaf-mt-xl" block size="large">
        {t('setup.btn_next')}
      </Button>
    </div>
  );
};

export default StepDeviceScan;
