/**
 * Resource Packs Tab — read-only overview of ResourcePacks bound to this
 * GameProfile's accounts (Spec v3 §2.5.2 Tab 5).
 *
 * Architecture §3.2: ResourcePack binds to GameAccount (not GameProfile) so
 * cross-server accounts can use different packs. Binding/unbinding is done
 * on the Accounts tab; this tab is read-only.
 */
import { useEffect, useState, useCallback } from 'react';
import { Alert, Table, Tag, Typography, Button, App } from 'antd';
import { ReloadOutlined, InfoCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchGameProfileResourcePacks } from '@/api/gameProfiles';
import type { ResourcePack } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';

const { Text } = Typography;

interface Props {
  profileId: number;
}

export default function ResourcePacksTab({ profileId }: Props) {
  const t = useTranslation();
  const { message } = App.useApp();
  const [data, setData] = useState<ResourcePack[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchGameProfileResourcePacks(profileId, { page, page_size: pageSize });
      setData(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      message.error(t('gameProfiles.tab_packs_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [profileId, page, pageSize, message, t]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnsType<ResourcePack> = [
    {
      title: t('gameProfiles.col_pack_name'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: t('gameProfiles.col_pack_version'),
      dataIndex: 'version',
      key: 'version',
      width: 120,
      render: (v: string) => <Tag color="blue">v{v}</Tag>,
    },
    {
      title: t('gameProfiles.col_pack_target_app'),
      dataIndex: 'target_app',
      key: 'target_app',
      width: 140,
      render: (text?: string) => (text ? <Tag>{text}</Tag> : <Text type="secondary">—</Text>),
    },
    {
      title: t('gameProfiles.col_pack_author'),
      dataIndex: 'author',
      key: 'author',
      width: 140,
      render: (text?: string) => (text ? <Text>{text}</Text> : <Text type="secondary">—</Text>),
    },
    {
      title: t('gameProfiles.col_pack_active'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      render: (active?: boolean) =>
        active ? (
          <Tag color="green">{t('gameProfiles.tag_active')}</Tag>
        ) : (
          <Tag color="default">{t('gameProfiles.tag_inactive')}</Tag>
        ),
    },
    {
      title: t('gameProfiles.col_pack_template_count'),
      dataIndex: 'template_count',
      key: 'template_count',
      width: 120,
      render: (n?: number) => <Tag>{n ?? 0}</Tag>,
    },
    {
      title: t('gameProfiles.col_pack_directory'),
      dataIndex: 'directory_path',
      key: 'directory_path',
      width: 260,
      ellipsis: true,
      render: (text: string) => <Text code>{text}</Text>,
    },
    {
      title: t('gameProfiles.col_pack_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => (
        <Text type="secondary">{dayjs(text).locale(getLocale()).format('YYYY-MM-DD HH:mm')}</Text>
      ),
    },
  ];

  return (
    <div>
      <Alert
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        title={t('gameProfiles.tab_resource_packs_hint')}
        className="gaf-mb-md"
      />
      <div className="gaf-mb-md gaf-flex" style={{ justifyContent: 'flex-end' }}>
        <Button size="small" icon={<ReloadOutlined />} onClick={load} loading={loading}>
          {t('gameProfiles.btn_refresh')}
        </Button>
      </div>
      <Table<ResourcePack>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 1200 }}
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
    </div>
  );
}
