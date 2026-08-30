/**
 * GameProfile Detail Page (Spec v3 §2.5.2)
 *
 * Layout:
 *   ┌────────────────────────────────────────────────────────────┐
 *   │  GameProfile: <name>                                       │
 *   │  [Edit] [Delete]                                           │
 *   │  Default Screenshot: wgc | Default Input: postmessage | ... │
 *   ├────────────────────────────────────────────────────────────┤
 *   │  Tabs: [Tasks] [Task Chains] [Devices] [Accounts]          │
 *   │        [Resource Packs]                                    │
 *   └────────────────────────────────────────────────────────────┘
 */
import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, Card, Descriptions, Popconfirm, Space, Tabs, Tag, Typography, App, Spin } from 'antd';
import {
  ArrowLeftOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchGameProfile, deleteGameProfile, dispatchRoutine, updateGameProfile } from '@/api/gameProfiles';
import type { GameProfile } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';
import GameProfileEditorModal from './components/GameProfileEditorModal';

import TasksTab from './components/TasksTab';
import TaskChainsTab from './components/TaskChainsTab';
import DevicesTab from './components/DevicesTab';
import AccountsTab from './components/AccountsTab';
import ResourcePacksTab from './components/ResourcePacksTab';

const { Title, Text } = Typography;

export function GameProfileDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const t = useTranslation();

  const [profile, setProfile] = useState<GameProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [dispatching, setDispatching] = useState(false);
  const [activeTab, setActiveTab] = useState('tasks');
  const [editorOpen, setEditorOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const profileId = id ? parseInt(id, 10) : NaN;

  const loadProfile = useCallback(async () => {
    if (Number.isNaN(profileId)) return;
    setLoading(true);
    try {
      const data = await fetchGameProfile(profileId);
      setProfile(data);
    } catch {
      message.error(t('gameProfiles.msg_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [profileId, message, t]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const handleDelete = async () => {
    if (!profile) return;
    try {
      await deleteGameProfile(profile.id);
      message.success(t('gameProfiles.msg_delete_success'));
      navigate('/game-profiles');
    } catch {
      message.error(t('gameProfiles.msg_delete_failed'));
    }
  };

  const handleDispatchRoutine = async () => {
    if (!profile) return;
    setDispatching(true);
    try {
      const result = await dispatchRoutine(profile.id);
      if (result.dispatched_count > 0) {
        message.success(
          t('gameProfiles.msg_dispatch_success', {
            count: result.dispatched_count,
            failed: result.failed_count,
          }),
        );
      } else {
        message.warning(t('gameProfiles.msg_dispatch_empty'));
      }
    } catch {
      message.error(t('gameProfiles.msg_dispatch_failed'));
    } finally {
      setDispatching(false);
    }
  };

  /** Inline edit handler — opens GameProfileEditorModal without navigating
   *  back to the list page. After save, refreshes the profile in place. */
  const handleEditSubmit = async (values: Record<string, unknown>) => {
    if (!profile) return;
    setSubmitting(true);
    try {
      await updateGameProfile(profile.id, values);
      message.success(t('gameProfiles.msg_update_success'));
      setEditorOpen(false);
      loadProfile();
    } catch {
      message.error(t('gameProfiles.msg_update_failed'));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <PageWrapper title={t('gameProfiles.detail_loading')}>
        <div className="gaf-flex gaf-justify-center" style={{ padding: '40px 0' }}>
          <Spin size="large" />
        </div>
      </PageWrapper>
    );
  }

  if (!profile) {
    return (
      <PageWrapper title={t('gameProfiles.detail_not_found')}>
        <Card>
          <Text type="secondary">{t('gameProfiles.detail_not_found_desc')}</Text>
          <div className="gaf-mt-lg">
            <Button type="primary" onClick={() => navigate('/game-profiles')}>
              {t('gameProfiles.btn_back_to_list')}
            </Button>
          </div>
        </Card>
      </PageWrapper>
    );
  }

  const tabItems = [
    {
      key: 'tasks',
      label: t('gameProfiles.tab_tasks'),
      children: <TasksTab profileId={profile.id} />,
    },
    {
      key: 'task_chains',
      label: t('gameProfiles.tab_task_chains'),
      children: (
        <TaskChainsTab
          profileId={profile.id}
          currentDefaultRoutineId={profile.default_task_chain ?? null}
          onRoutineChanged={loadProfile}
        />
      ),
    },
    {
      key: 'devices',
      label: t('gameProfiles.tab_devices'),
      children: <DevicesTab profileId={profile.id} defaultRoutineId={profile.default_task_chain ?? null} />,
    },
    {
      key: 'accounts',
      label: t('gameProfiles.tab_accounts'),
      children: <AccountsTab profileId={profile.id} />,
    },
    {
      key: 'resource_packs',
      label: t('gameProfiles.tab_resource_packs'),
      children: <ResourcePacksTab profileId={profile.id} />,
    },
  ];

  return (
    <PageWrapper
      title={
        <Space>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/game-profiles')}
            aria-label="返回游戏配置列表"
          />
          <Title level={4} style={{ margin: 0 }}>
            {profile.game_name}
          </Title>
        </Space>
      }
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadProfile}>
            {t('gameProfiles.btn_refresh')}
          </Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={dispatching}
            onClick={handleDispatchRoutine}
            disabled={!profile.default_task_chain}
            title={profile.default_task_chain ? undefined : t('gameProfiles.tip_no_default_task_chain')}
          >
            {t('gameProfiles.btn_dispatch_routine')}
          </Button>
          <Button icon={<EditOutlined />} onClick={() => setEditorOpen(true)}>
            {t('gameProfiles.btn_edit')}
          </Button>
          <Popconfirm
            title={t('gameProfiles.confirm_delete')}
            description={t('gameProfiles.confirm_delete_desc', { name: profile.game_name })}
            onConfirm={handleDelete}
            okText={t('gameProfiles.btn_delete')}
            cancelText={t('gameProfiles.btn_cancel')}
            okButtonProps={{ danger: true }}
          >
            <Button danger icon={<DeleteOutlined />}>
              {t('gameProfiles.btn_delete')}
            </Button>
          </Popconfirm>
        </Space>
      }
    >
      <Card className="gaf-mb-lg">
        <Descriptions column={3} size="small">
          <Descriptions.Item label={t('gameProfiles.col_default_task_chain')}>
            {(profile as GameProfile & { default_task_chain_name?: string }).default_task_chain_name ? (
              <Tag color="green">
                {(profile as GameProfile & { default_task_chain_name?: string }).default_task_chain_name}
              </Tag>
            ) : (
              <Text type="secondary">—</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label={t('gameProfiles.col_default_screenshot_method')}>
            {profile.default_screenshot_method ? (
              <Tag color="blue">{profile.default_screenshot_method}</Tag>
            ) : (
              <Text type="secondary">auto</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label={t('gameProfiles.col_default_input_method')}>
            {profile.default_input_method ? (
              <Tag color="cyan">{profile.default_input_method}</Tag>
            ) : (
              <Text type="secondary">auto</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label={t('gameProfiles.col_default_control_mode')}>
            {profile.default_control_mode ? (
              <Tag color="purple">{profile.default_control_mode}</Tag>
            ) : (
              <Text type="secondary">auto</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label={t('gameProfiles.col_ocr_language')}>
            <Tag>{profile.ocr_language}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('gameProfiles.col_reference_resolution')}>
            <Text code>
              {profile.ui_reference_resolution?.w}×{profile.ui_reference_resolution?.h}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label={t('gameProfiles.col_resolution_strategy')}>
            <Tag color="geekblue">{profile.resolution_strategy}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('gameProfiles.col_known_popups')}>
            {(profile.known_popups?.length ?? 0) > 0 ? (
              <Space wrap>
                {profile.known_popups!.map((p) => (
                  <Tag key={p}>{p}</Tag>
                ))}
              </Space>
            ) : (
              <Text type="secondary">—</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label={t('gameProfiles.col_created_at')}>
            <Text type="secondary">{dayjs(profile.created_at).locale(getLocale()).format('YYYY-MM-DD HH:mm')}</Text>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} destroyOnHidden />
      </Card>

      <GameProfileEditorModal
        open={editorOpen}
        profile={profile ?? undefined}
        submitting={submitting}
        onOk={handleEditSubmit}
        onCancel={() => setEditorOpen(false)}
      />
    </PageWrapper>
  );
}

export default GameProfileDetailPage;
