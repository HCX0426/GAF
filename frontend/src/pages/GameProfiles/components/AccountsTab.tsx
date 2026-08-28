/**
 * Accounts Tab — list GameAccounts belonging to this GameProfile (Spec v3 §2.5.2 Tab 4)
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import { Table, Tag, Typography, Button, App, Popconfirm } from 'antd';
import { ReloadOutlined, PlusOutlined, DisconnectOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchGameProfileAccounts, unbindAccount } from '@/api/gameProfiles';
import type { GameAccount } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';
import { BindResourceModal } from './BindResourceModal';

const { Text } = Typography;

interface Props {
  profileId: number;
}

export default function AccountsTab({ profileId }: Props) {
  const t = useTranslation();
  const { message } = App.useApp();
  const [data, setData] = useState<GameAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [bindOpen, setBindOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchGameProfileAccounts(profileId, { page, page_size: pageSize });
      setData(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      message.error(t('gameProfiles.tab_accounts_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [profileId, page, pageSize, message, t]);

  useEffect(() => {
    load();
  }, [load]);

  const handleUnbind = useCallback(
    async (accountId: number) => {
      try {
        await unbindAccount(profileId, accountId);
        message.success(t('gameProfiles.unbind_success'));
        load();
      } catch (err: unknown) {
        const detail = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
        message.error(detail || t('gameProfiles.unbind_failed'));
      }
    },
    [profileId, message, t, load],
  );

  const excludeIds = useMemo(() => data.map((x) => x.id), [data]);

  const columns: ColumnsType<GameAccount> = [
    {
      title: t('gameProfiles.col_account_username'),
      dataIndex: 'username',
      key: 'username',
      width: 200,
      ellipsis: true,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: t('gameProfiles.col_account_server_region'),
      dataIndex: 'server_region',
      key: 'server_region',
      width: 140,
      render: (text: string) => <Tag>{text}</Tag>,
    },
    {
      title: t('gameProfiles.col_account_login_method'),
      dataIndex: 'login_method',
      key: 'login_method',
      width: 120,
      render: (m: string) => <Tag color="blue">{m}</Tag>,
    },
    {
      title: t('gameProfiles.col_account_status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          ok: 'green',
          warn: 'orange',
          error: 'red',
          unknown: 'default',
        };
        return <Tag color={colorMap[status] || 'default'}>{status}</Tag>;
      },
    },
    {
      title: t('gameProfiles.col_account_resource_pack'),
      dataIndex: 'resource_pack',
      key: 'resource_pack',
      width: 180,
      render: (rp?: { id: number; name: string; version: string } | null) =>
        rp ? (
          <Tag color="geekblue">
            {rp.name} v{rp.version}
          </Tag>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: t('gameProfiles.col_account_login_count'),
      dataIndex: 'login_count',
      key: 'login_count',
      width: 100,
      render: (n: number) => <Text>{n}</Text>,
    },
    {
      title: t('gameProfiles.col_account_execution_count'),
      dataIndex: 'execution_count',
      key: 'execution_count',
      width: 120,
      render: (n: number) => <Text>{n}</Text>,
    },
    {
      title: t('gameProfiles.col_account_last_execution_time'),
      dataIndex: 'last_execution_time',
      key: 'last_execution_time',
      width: 160,
      render: (text?: string | null) =>
        text ? (
          <Text type="secondary">{dayjs(text).locale(getLocale()).format('YYYY-MM-DD HH:mm')}</Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: t('gameProfiles.col_account_active'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (active?: boolean) =>
        active ? (
          <Tag color="green">{t('gameProfiles.tag_active')}</Tag>
        ) : (
          <Tag color="default">{t('gameProfiles.tag_inactive')}</Tag>
        ),
    },
    {
      title: t('gameProfiles.col_actions'),
      key: 'actions',
      width: 120,
      render: (_: unknown, record: GameAccount) => (
        <Popconfirm
          title={t('gameProfiles.unbind_account_confirm')}
          onConfirm={() => handleUnbind(record.id)}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
        >
          <Button type="link" size="small" danger icon={<DisconnectOutlined />}>
            {t('gameProfiles.btn_unbind')}
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <div className="gaf-mb-md gaf-flex-between">
        <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => setBindOpen(true)}>
          {t('gameProfiles.btn_add_account')}
        </Button>
        <Button size="small" icon={<ReloadOutlined />} onClick={load} loading={loading}>
          {t('gameProfiles.btn_refresh')}
        </Button>
      </div>
      <Table<GameAccount>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 1320 }}
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
      <BindResourceModal
        open={bindOpen}
        profileId={profileId}
        resourceType="account"
        excludeIds={excludeIds}
        onClose={() => setBindOpen(false)}
        onBound={load}
      />
    </div>
  );
}
