/**
 * Task Chains Tab — list TaskChains belonging to this GameProfile (Spec v3 §2.5.2 Tab 2)
 * Allows setting a chain as the default routine for this profile.
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tag, Typography, Button, Space, App, Popconfirm } from 'antd';
import {
  ReloadOutlined,
  StarOutlined,
  StarFilled,
  EditOutlined,
  PlusOutlined,
  DisconnectOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchGameProfileTaskChains, setDefaultRoutine, unbindTaskChain } from '@/api/gameProfiles';
import type { TaskChain } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';
import { BindResourceModal } from './BindResourceModal';

const { Text } = Typography;

interface Props {
  profileId: number;
  currentDefaultRoutineId: number | null;
  onRoutineChanged?: () => void;
}

export default function TaskChainsTab({ profileId, currentDefaultRoutineId, onRoutineChanged }: Props) {
  const t = useTranslation();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [data, setData] = useState<TaskChain[]>([]);
  const [loading, setLoading] = useState(false);
  const [settingDefault, setSettingDefault] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [bindOpen, setBindOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchGameProfileTaskChains(profileId, { page, page_size: pageSize });
      setData(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      message.error(t('gameProfiles.tab_chains_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [profileId, page, pageSize, message, t]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSetDefault = async (chain: TaskChain) => {
    setSettingDefault(true);
    try {
      await setDefaultRoutine(profileId, chain.id);
      message.success(t('gameProfiles.msg_set_default_success', { name: chain.name }));
      onRoutineChanged?.();
      load();
    } catch {
      message.error(t('gameProfiles.msg_set_default_failed'));
    } finally {
      setSettingDefault(false);
    }
  };

  const handleUnbind = useCallback(
    async (chainId: number) => {
      try {
        await unbindTaskChain(profileId, chainId);
        message.success(t('gameProfiles.unbind_success'));
        onRoutineChanged?.();
        load();
      } catch (err: unknown) {
        const detail = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
        message.error(detail || t('gameProfiles.unbind_failed'));
      }
    },
    [profileId, message, t, load, onRoutineChanged],
  );

  const excludeIds = useMemo(() => data.map((x) => x.id), [data]);

  const columns: ColumnsType<TaskChain> = [
    {
      title: t('gameProfiles.col_chain_name'),
      dataIndex: 'name',
      key: 'name',
      width: 220,
      ellipsis: true,
      render: (text: string, record) => (
        <Space>
          <Text strong>{text}</Text>
          {record.is_default && <Tag color="gold">{t('gameProfiles.tag_default')}</Tag>}
        </Space>
      ),
    },
    {
      title: t('gameProfiles.col_chain_description'),
      dataIndex: 'description',
      key: 'description',
      width: 260,
      ellipsis: true,
      render: (text: string) => <Text type="secondary">{text || '—'}</Text>,
    },
    {
      title: t('gameProfiles.col_chain_node_count'),
      dataIndex: 'node_count',
      key: 'node_count',
      width: 100,
      render: (n: number) => <Tag>{n}</Tag>,
    },
    {
      title: t('gameProfiles.col_chain_enabled'),
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 100,
      render: (enabled?: boolean) =>
        enabled ? (
          <Tag color="green">{t('gameProfiles.tag_enabled')}</Tag>
        ) : (
          <Tag color="default">{t('gameProfiles.tag_disabled')}</Tag>
        ),
    },
    {
      title: t('gameProfiles.col_chain_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => (
        <Text type="secondary">{dayjs(text).locale(getLocale()).format('YYYY-MM-DD HH:mm')}</Text>
      ),
    },
    {
      title: t('gameProfiles.col_actions'),
      key: 'actions',
      width: 280,
      render: (_: unknown, record: TaskChain) => (
        <Space>
          {record.is_default || currentDefaultRoutineId === record.id ? (
            <Button type="link" size="small" icon={<StarFilled />} disabled>
              {t('gameProfiles.btn_is_default')}
            </Button>
          ) : (
            <Popconfirm
              title={t('gameProfiles.confirm_set_default')}
              description={t('gameProfiles.confirm_set_default_desc', { name: record.name })}
              onConfirm={() => handleSetDefault(record)}
              okText={t('gameProfiles.btn_set_default')}
              cancelText={t('gameProfiles.btn_cancel')}
            >
              <Button type="link" size="small" icon={<StarOutlined />} loading={settingDefault}>
                {t('gameProfiles.btn_set_default')}
              </Button>
            </Popconfirm>
          )}
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => navigate(`/ops/scheduler/dag/${record.id}`)}
          >
            {t('gameProfiles.btn_edit')}
          </Button>
          <Popconfirm
            title={t('gameProfiles.unbind_task_chain_confirm')}
            onConfirm={() => handleUnbind(record.id)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Button type="link" size="small" danger icon={<DisconnectOutlined />}>
              {t('gameProfiles.btn_unbind')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="gaf-mb-md gaf-flex-between">
        <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => setBindOpen(true)}>
          {t('gameProfiles.btn_add_task_chain')}
        </Button>
        <Button size="small" icon={<ReloadOutlined />} onClick={load} loading={loading}>
          {t('gameProfiles.btn_refresh')}
        </Button>
      </div>
      <Table<TaskChain>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 1000 }}
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
        resourceType="task_chain"
        excludeIds={excludeIds}
        onClose={() => setBindOpen(false)}
        onBound={() => {
          load();
          onRoutineChanged?.();
        }}
      />
    </div>
  );
}
