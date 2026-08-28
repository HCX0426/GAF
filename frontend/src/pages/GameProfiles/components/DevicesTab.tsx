/**
 * Devices Tab — list Devices bound to this GameProfile (Spec v3 §2.5.2 Tab 3)
 *
 * Stage 4.1: per-device "排任务" button opens DispatchRoutineModal (spec v3 §2.6).
 */
import { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Typography, Button, App } from 'antd';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchGameProfileDevices } from '@/api/gameProfiles';
import type { Device } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';
import DispatchRoutineModal from '@/components/GameProfile/DispatchRoutineModal';

const { Text } = Typography;

interface Props {
  profileId: number;
  defaultRoutineId?: number | null;
}

export default function DevicesTab({ profileId, defaultRoutineId }: Props) {
  const t = useTranslation();
  const { message } = App.useApp();
  const [data, setData] = useState<Device[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [dispatchDevice, setDispatchDevice] = useState<Device | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchGameProfileDevices(profileId, { page, page_size: pageSize });
      setData(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      message.error(t('gameProfiles.tab_devices_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [profileId, page, pageSize, message, t]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnsType<Device> = [
    {
      title: t('gameProfiles.col_device_name'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: t('gameProfiles.col_device_type'),
      dataIndex: 'device_type',
      key: 'device_type',
      width: 120,
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: t('gameProfiles.col_device_status'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const color = status === 'online' ? 'green' : status === 'busy' ? 'orange' : 'default';
        return <Tag color={color}>{status}</Tag>;
      },
    },
    {
      title: t('gameProfiles.col_device_adb_serial'),
      dataIndex: 'adb_serial',
      key: 'adb_serial',
      width: 180,
      render: (text: string) => (text ? <Text code>{text}</Text> : <Text type="secondary">—</Text>),
    },
    {
      title: t('gameProfiles.col_device_resolution'),
      key: 'resolution',
      width: 140,
      render: (_: unknown, record: Device) => {
        if (record.resolution_display) return <Text code>{record.resolution_display}</Text>;
        if (record.resolution_width && record.resolution_height) {
          return (
            <Text code>
              {record.resolution_width}×{record.resolution_height}
            </Text>
          );
        }
        return <Text type="secondary">—</Text>;
      },
    },
    {
      title: t('gameProfiles.col_device_screenshot_method'),
      dataIndex: 'screenshot_method',
      key: 'screenshot_method',
      width: 140,
      render: (m: string) => (m ? <Tag color="blue">{m}</Tag> : <Text type="secondary">auto</Text>),
    },
    {
      title: t('gameProfiles.col_device_control_mode'),
      dataIndex: 'control_mode',
      key: 'control_mode',
      width: 140,
      render: (m: string) => (m ? <Tag color="purple">{m}</Tag> : <Text type="secondary">auto</Text>),
    },
    {
      title: t('gameProfiles.col_device_last_heartbeat'),
      dataIndex: 'last_heartbeat',
      key: 'last_heartbeat',
      width: 160,
      render: (text?: string) =>
        text ? (
          <Text type="secondary">{dayjs(text).locale(getLocale()).format('YYYY-MM-DD HH:mm')}</Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: t('gameProfiles.col_actions'),
      key: 'actions',
      width: 120,
      fixed: 'right',
      render: (_: unknown, record: Device) => (
        <Button
          size="small"
          type="primary"
          ghost
          icon={<ThunderboltOutlined />}
          onClick={() => setDispatchDevice(record)}
          disabled={record.status !== 'online'}
          title={record.status !== 'online' ? t('gameProfiles.dispatch_device_offline') : undefined}
        >
          {t('gameProfiles.btn_dispatch')}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div className="gaf-mb-md gaf-flex" style={{ justifyContent: 'flex-end' }}>
        <Button size="small" icon={<ReloadOutlined />} onClick={load} loading={loading}>
          {t('gameProfiles.btn_refresh')}
        </Button>
      </div>
      <Table<Device>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 1220 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />
      <DispatchRoutineModal
        open={dispatchDevice !== null}
        onClose={() => setDispatchDevice(null)}
        profileId={profileId}
        device={dispatchDevice}
        defaultRoutineId={defaultRoutineId}
      />
    </div>
  );
}
