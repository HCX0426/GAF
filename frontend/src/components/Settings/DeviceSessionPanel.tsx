/**
 * DeviceSessionPanel — login device management panel (A5)
 *
 * column out current user has active session, supports:
 * - view device name /IP/ last activity time / login time
 * - mark current session
 * - kick offline specific session
 * - batch kick below except current outside has session
 */

import { useState, useEffect, useCallback } from 'react';
import { Card, Table, Button, Tag, Space, Typography, App, Popconfirm, Tooltip, Empty } from 'antd';
import {
  DesktopOutlined,
  MobileOutlined,
  GlobalOutlined,
  ApiOutlined,
  PoweroffOutlined,
  LogoutOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { fetchSessions, kickSession, logoutAllOtherSessions } from '@/api/auth';
import type { UserSession } from '@/types/models';
import { useTranslation } from '@/i18n';

const { Title, Text } = Typography;

/** Format ISO datetime string to local readable format */
function formatDateTime(iso: string): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

/** Device type icon and color mapping */
function getDeviceTypeMeta(type: UserSession['device_type']) {
  switch (type) {
    case 'web':
      return { icon: <GlobalOutlined />, color: 'blue', label: 'Web' };
    case 'mobile':
      return { icon: <MobileOutlined />, color: 'purple', label: '移动端' };
    case 'desktop':
      return { icon: <DesktopOutlined />, color: 'cyan', label: '桌面端' };
    case 'api':
      return { icon: <ApiOutlined />, color: 'orange', label: 'API' };
    default:
      return { icon: <GlobalOutlined />, color: 'default', label: '未知' };
  }
}

/** login device management panel */
export function DeviceSessionPanel() {
  const { message } = App.useApp();
  const t = useTranslation();
  const [sessions, setSessions] = useState<UserSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [kickingId, setKickingId] = useState<number | null>(null);
  const [bulkLoading, setBulkLoading] = useState(false);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchSessions();
      setSessions(data);
    } catch {
      message.error(t('settings.sessions_fetch_failed'));
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      try {
        const data = await fetchSessions();
        if (!cancelled) setSessions(data);
      } catch {
        if (!cancelled) message.error(t('settings.sessions_fetch_failed'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [message]);

  /** Kick a single session */
  const handleKick = async (id: number) => {
    setKickingId(id);
    try {
      const result = await kickSession(id);
      message.success(result.detail || t('settings.session_kicked'));
      await loadSessions();
    } catch {
      message.error(t('settings.session_kick_failed'));
    } finally {
      setKickingId(null);
    }
  };

  /** Kick all other sessions except current */
  const handleLogoutAllOthers = async () => {
    setBulkLoading(true);
    try {
      const result = await logoutAllOtherSessions();
      message.success(result.detail || t('settings.sessions_others_kicked'));
      await loadSessions();
    } catch {
      message.error(t('settings.sessions_bulk_kick_failed'));
    } finally {
      setBulkLoading(false);
    }
  };

  const otherActiveCount = sessions.filter((s) => !s.is_current).length;

  const columns: ColumnsType<UserSession> = [
    {
      title: '设备',
      dataIndex: 'device_name',
      key: 'device_name',
      render: (name: string, record) => {
        const meta = getDeviceTypeMeta(record.device_type);
        return (
          <Space>
            {meta.icon}
            <div>
              <div>
                <Text strong>{name || '未知设备'}</Text>
                {record.is_current && (
                  <Tag color="green" className="gaf-ml-sm">
                    当前会话
                  </Tag>
                )}
              </div>
              <Tag color={meta.color} className="gaf-mt-xs">
                {meta.label}
              </Tag>
            </div>
          </Space>
        );
      },
    },
    {
      title: 'IP 地址',
      dataIndex: 'ip_address',
      key: 'ip_address',
      render: (ip: string | null) => ip || '-',
    },
    {
      title: '位置',
      dataIndex: 'location',
      key: 'location',
      render: (loc: string) => loc || '-',
    },
    {
      title: '最后活动',
      dataIndex: 'last_activity',
      key: 'last_activity',
      render: (iso: string) => (
        <Tooltip title={formatDateTime(iso)}>
          <Space size={4}>
            <ClockCircleOutlined />
            <Text type="secondary">{formatDateTime(iso)}</Text>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: '登录时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (iso: string) => <Text type="secondary">{formatDateTime(iso)}</Text>,
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, record) => {
        if (record.is_current) {
          return <Tag color="default">当前设备</Tag>;
        }
        return (
          <Popconfirm
            title="确认踢下线此设备？"
            description="该设备的会话将立即失效。"
            onConfirm={() => handleKick(record.id)}
            okText="确认"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button danger size="small" icon={<PoweroffOutlined />} loading={kickingId === record.id}>
              踢下线
            </Button>
          </Popconfirm>
        );
      },
    },
  ];

  return (
    <div style={{ maxWidth: 900 }}>
      <Title level={5}>
        <DesktopOutlined /> 登录设备管理
      </Title>

      <Card>
        <Space orientation="vertical" size="middle" className="gaf-w-full">
          <div className="gaf-flex-between">
            <div>
              <Text strong>活跃会话列表</Text>
              <br />
              <Text type="secondary">
                共 {sessions.length} 个活跃会话，其中 {otherActiveCount} 个其他设备
              </Text>
            </div>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={loadSessions} loading={loading}>
                刷新
              </Button>
              {otherActiveCount > 0 && (
                <Popconfirm
                  title={`确认踢下线其他 ${otherActiveCount} 个会话？`}
                  description="除当前会话外，所有其他设备将立即下线。"
                  onConfirm={handleLogoutAllOthers}
                  okText="确认"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                >
                  <Button danger icon={<LogoutOutlined />} loading={bulkLoading}>
                    踢下线所有其他会话
                  </Button>
                </Popconfirm>
              )}
            </Space>
          </div>

          <Table
            columns={columns}
            dataSource={sessions}
            rowKey="id"
            loading={loading}
            pagination={false}
            size="middle"
            locale={{
              emptyText: <Empty description="暂无活跃会话" />,
            }}
          />
        </Space>
      </Card>
    </div>
  );
}

export default DeviceSessionPanel;
