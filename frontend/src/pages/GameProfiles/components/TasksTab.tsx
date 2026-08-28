/**
 * Tasks Tab — list Tasks belonging to this GameProfile (Spec v3 §2.5.2 Tab 1)
 *
 * Supports bind/unbind: the "+ Add" button opens BindResourceModal to attach
 * an existing Task; the "Unbind" action removes it from this profile (the
 * Task itself is not deleted).
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tag, Typography, Button, Space, App, Popconfirm } from 'antd';
import { ReloadOutlined, EditOutlined, PlusOutlined, DisconnectOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchGameProfileTasks, unbindTask } from '@/api/gameProfiles';
import type { Task } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';
import { BindResourceModal } from './BindResourceModal';

const { Text } = Typography;

interface Props {
  profileId: number;
}

export default function TasksTab({ profileId }: Props) {
  const t = useTranslation();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [data, setData] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [bindOpen, setBindOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchGameProfileTasks(profileId, { page, page_size: pageSize });
      setData(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      message.error(t('gameProfiles.tab_tasks_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [profileId, page, pageSize, message, t]);

  useEffect(() => {
    load();
  }, [load]);

  const handleUnbind = useCallback(
    async (taskId: number) => {
      try {
        await unbindTask(profileId, taskId);
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

  const columns: ColumnsType<Task> = [
    {
      title: t('gameProfiles.col_task_name'),
      dataIndex: 'name',
      key: 'name',
      width: 220,
      ellipsis: true,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: t('gameProfiles.col_task_execution_mode'),
      dataIndex: 'execution_mode',
      key: 'execution_mode',
      width: 120,
      render: (mode?: string) => (mode ? <Tag>{mode}</Tag> : <Text type="secondary">—</Text>),
    },
    {
      title: t('gameProfiles.col_task_enabled'),
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
      title: t('gameProfiles.col_task_created_at'),
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
      width: 180,
      render: (_: unknown, record: Task) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => navigate(`/tasks/${record.id}/edit`)}>
            {t('gameProfiles.btn_edit')}
          </Button>
          <Popconfirm
            title={t('gameProfiles.unbind_task_confirm')}
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
          {t('gameProfiles.btn_add_task')}
        </Button>
        <Button size="small" icon={<ReloadOutlined />} onClick={load} loading={loading}>
          {t('gameProfiles.btn_refresh')}
        </Button>
      </div>
      <Table<Task>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 900 }}
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
        resourceType="task"
        excludeIds={excludeIds}
        onClose={() => setBindOpen(false)}
        onBound={load}
      />
    </div>
  );
}
