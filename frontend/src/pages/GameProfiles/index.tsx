/**
 * Game Profile list page (Spec v3 §2.5.1)
 *
 * Promoted from /system/game-profiles to top-level /game-profiles.
 * Shows GameProfile list with v3 fields: default_routine, default_screenshot_method,
 * default_input_method, default_control_mode.
 *
 * Clicking a row navigates to /game-profiles/:id (detail page with 6 tabs).
 */
import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Button, Space, Tag, Popconfirm, Card, App, Typography, Input } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchGameProfiles, createGameProfile, updateGameProfile, deleteGameProfile } from '@/api/gameProfiles';
import type { GameProfile } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';
import GameProfileEditorModal from './components/GameProfileEditorModal';
import { useGameProfileOptions } from './options';

const { Text } = Typography;

export function GameProfilesPage() {
  const { message } = App.useApp();
  const t = useTranslation();
  const navigate = useNavigate();
  const { screenshotMethods, inputMethods, controlModes, ocrLangOptions, resolutionStrategyOptions } =
    useGameProfileOptions();
  const [profiles, setProfiles] = useState<GameProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [searchText, setSearchText] = useState('');

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingProfile, setEditingProfile] = useState<GameProfile | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  const loadProfiles = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchGameProfiles({
        page,
        page_size: pageSize,
        search: searchText || undefined,
      });
      setProfiles(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      message.error(t('gameProfiles.msg_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchText, message, t]);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  const handleCreate = () => {
    setEditingProfile(undefined);
    setEditorOpen(true);
  };

  const handleEdit = (record: GameProfile) => {
    setEditingProfile(record);
    setEditorOpen(true);
  };

  const handleClose = () => {
    setEditorOpen(false);
    setEditingProfile(undefined);
  };

  const handleSubmit = async (values: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      if (editingProfile) {
        await updateGameProfile(editingProfile.id, values);
        message.success(t('gameProfiles.msg_update_success'));
      } else {
        await createGameProfile(values);
        message.success(t('gameProfiles.msg_create_success'));
      }
      setEditorOpen(false);
      loadProfiles();
    } catch {
      message.error(editingProfile ? t('gameProfiles.msg_update_failed') : t('gameProfiles.msg_create_failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (record: GameProfile) => {
    try {
      await deleteGameProfile(record.id);
      message.success(t('gameProfiles.msg_delete_success'));
      loadProfiles();
    } catch {
      message.error(t('gameProfiles.msg_delete_failed'));
    }
  };

  const handleViewDetail = (record: GameProfile) => {
    navigate(`/game-profiles/${record.id}`);
  };

  const columns: ColumnsType<GameProfile> = [
    {
      title: t('gameProfiles.col_game_name'),
      dataIndex: 'game_name',
      key: 'game_name',
      width: 200,
      ellipsis: true,
      render: (text: string, record) => (
        <Button type="link" onClick={() => handleViewDetail(record)} style={{ padding: 0 }}>
          <Text strong>{text}</Text>
        </Button>
      ),
    },
    {
      title: t('gameProfiles.col_default_routine'),
      dataIndex: 'default_routine_name',
      key: 'default_routine_name',
      width: 160,
      render: (name?: string | null) => (name ? <Tag color="green">{name}</Tag> : <Text type="secondary">—</Text>),
    },
    {
      title: t('gameProfiles.col_default_screenshot_method'),
      dataIndex: 'default_screenshot_method',
      key: 'default_screenshot_method',
      width: 140,
      render: (method?: string) => {
        if (!method) return <Text type="secondary">auto</Text>;
        const option = screenshotMethods.find((o) => o.value === method);
        return <Tag color="blue">{option?.label || method}</Tag>;
      },
    },
    {
      title: t('gameProfiles.col_default_input_method'),
      dataIndex: 'default_input_method',
      key: 'default_input_method',
      width: 140,
      render: (method?: string) => {
        if (!method) return <Text type="secondary">auto</Text>;
        const option = inputMethods.find((o) => o.value === method);
        return <Tag color="cyan">{option?.label || method}</Tag>;
      },
    },
    {
      title: t('gameProfiles.col_default_control_mode'),
      dataIndex: 'default_control_mode',
      key: 'default_control_mode',
      width: 120,
      render: (mode?: string) => {
        if (!mode) return <Text type="secondary">auto</Text>;
        const option = controlModes.find((o) => o.value === mode);
        return <Tag color="purple">{option?.label || mode}</Tag>;
      },
    },
    {
      title: t('gameProfiles.col_ocr_language'),
      dataIndex: 'ocr_language',
      key: 'ocr_language',
      width: 100,
      render: (lang: string) => {
        const option = ocrLangOptions.find((o) => o.value === lang);
        return <Tag>{option?.label || lang}</Tag>;
      },
    },
    {
      title: t('gameProfiles.col_reference_resolution'),
      dataIndex: 'ui_reference_resolution',
      key: 'ui_reference_resolution',
      width: 140,
      render: (res: { w: number; h: number }) => {
        if (!res) return '-';
        return (
          <Text code>
            {res.w}×{res.h}
          </Text>
        );
      },
    },
    {
      title: t('gameProfiles.col_resolution_strategy'),
      dataIndex: 'resolution_strategy',
      key: 'resolution_strategy',
      width: 150,
      render: (strategy: string) => {
        const option = resolutionStrategyOptions.find((o) => o.value === strategy);
        return <Tag color="geekblue">{option?.label || strategy}</Tag>;
      },
    },
    {
      title: t('gameProfiles.col_known_popups'),
      dataIndex: 'known_popups',
      key: 'known_popups',
      width: 200,
      ellipsis: true,
      render: (popups: string[]) => {
        if (!popups || popups.length === 0) return <Text type="secondary">{t('gameProfiles.none')}</Text>;
        return <Text ellipsis>{popups.join(', ')}</Text>;
      },
    },
    {
      title: t('gameProfiles.col_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => (
        <Text type="secondary">{dayjs(text).locale(getLocale()).format('YYYY-MM-DD HH:mm')}</Text>
      ),
    },
    {
      title: t('gameProfiles.col_actions'),
      key: 'actions',
      width: 220,
      fixed: 'right' as const,
      render: (_: unknown, record: GameProfile) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleViewDetail(record)}>
            {t('gameProfiles.btn_view_detail')}
          </Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            {t('gameProfiles.btn_edit')}
          </Button>
          <Popconfirm
            title={t('gameProfiles.confirm_delete')}
            description={t('gameProfiles.confirm_delete_desc', { name: record.game_name })}
            onConfirm={() => handleDelete(record)}
            okText={t('gameProfiles.btn_delete')}
            cancelText={t('gameProfiles.btn_cancel')}
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              {t('gameProfiles.btn_delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper
      title={t('gameProfiles.page_title')}
      titleIcon={<EditOutlined />}
      extra={
        <Space>
          <Input.Search
            placeholder={t('gameProfiles.search_placeholder')}
            allowClear
            className="gaf-w-200"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={() => {
              setPage(1);
              loadProfiles();
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => loadProfiles()}>
            {t('gameProfiles.btn_refresh')}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            {t('gameProfiles.btn_create')}
          </Button>
        </Space>
      }
    >
      <Text type="secondary" className="gaf-mb-lg gaf-display-block">
        {t('gameProfiles.page_desc')}
      </Text>

      <Card>
        <Table<GameProfile>
          rowKey="id"
          columns={columns}
          dataSource={profiles}
          loading={loading}
          scroll={{ x: 1400 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (total) => t('gameProfiles.total_count', { count: total }),
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>

      <GameProfileEditorModal
        open={editorOpen}
        profile={editingProfile}
        submitting={submitting}
        onOk={handleSubmit}
        onCancel={handleClose}
      />
    </PageWrapper>
  );
}

export default GameProfilesPage;
