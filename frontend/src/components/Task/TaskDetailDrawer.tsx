import { Drawer, Card, Tag, Typography, Space, Button, Collapse, Descriptions, Empty, theme as antTheme } from 'antd';
import {
  EditOutlined,
  PlayCircleOutlined,
  CopyOutlined,
  InfoCircleOutlined,
  AppstoreOutlined,
  ClockCircleOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { Task } from '@/types/models';
import { useTranslation } from '@/i18n';

const { Title, Paragraph, Text } = Typography;

/** Props interface for TaskDetailDrawer component */
interface TaskDetailDrawerProps {
  open: boolean;
  task: Task | null;
  onClose: () => void;
  onEdit?: (task: Task) => void;
  onExecute?: (task: Task) => void;
  onClone?: (task: Task) => void;
}

/**
 * TaskDetailDrawer component for displaying detailed task information
 * Provides a side drawer with comprehensive task details including:
 * - Basic information (name, description, mode, status, tags)
 * - Associated resources (resource packs, game account)
 * - Timestamps (created/updated times)
 * - Pipeline definition (collapsible JSON view)
 * - Action buttons (edit, execute, clone)
 */
export function TaskDetailDrawer({ open, task, onClose, onEdit, onExecute, onClone }: TaskDetailDrawerProps) {
  const { token } = antTheme.useToken();
  const t = useTranslation();

  /** execution mode → tag color. Stable per-mode, doesn't need locale. */
  const getExecutionModeColor = (mode: string): string => {
    switch (mode) {
      case 'pipeline':
        return 'blue';
      case 'state_machine':
        return 'green';
      default:
        return 'default';
    }
  };

  /** execution mode → localized label. */
  const getExecutionModeLabel = (mode: string): string => {
    switch (mode) {
      case 'pipeline':
        return t('tasks.detail_execution_mode_pipeline');
      case 'state_machine':
        return t('tasks.detail_execution_mode_state_machine');
      default:
        return mode;
    }
  };

  /** Render basic information section with task metadata */
  const renderBasicInfo = () => (
    <Card
      size="small"
      title={
        <Space>
          <InfoCircleOutlined />
          <Text strong>{t('tasks.detail_section_basic')}</Text>
        </Space>
      }
      className="gaf-mb-lg"
    >
      <div className="gaf-mb-md">
        <Title level={5} className="gaf-mb-sm">
          {task?.name || t('tasks.detail_unnamed')}
        </Title>
        <Paragraph
          ellipsis={{ rows: 3, expandable: true, symbol: t('tasks.detail_expand') }}
          className="gaf-mb-md"
          style={{ color: token.colorTextSecondary }}
        >
          {task?.description || t('tasks.detail_no_desc')}
        </Paragraph>
      </div>

      <Space wrap size={[8, 8]}>
        <Tag color={getExecutionModeColor(task?.execution_mode || '')}>
          {t('tasks.detail_execution_mode_label')}: {getExecutionModeLabel(task?.execution_mode || '')}
        </Tag>
        <Tag color={task?.is_enabled ? 'success' : 'default'}>
          {task?.is_enabled ? t('tasks.detail_enabled') : t('tasks.detail_disabled')}
        </Tag>
      </Space>

      {Array.isArray(task?.tags) && (task!.tags as string[]).length > 0 && (
        <div className="gaf-mt-md">
          <Text type="secondary" className="gaf-text-xs gaf-mr-sm">
            {t('tasks.detail_tags_label')}:
          </Text>
          <Space wrap size={[6, 6]}>
            {(task!.tags as string[]).map((tag: string) => (
              <Tag key={tag} color="processing">
                {tag}
              </Tag>
            ))}
          </Space>
        </div>
      )}
    </Card>
  );

  /** Render associated resources section showing resource packs and game account binding */
  const renderAssociatedResources = () => (
    <Card
      size="small"
      title={
        <Space>
          <AppstoreOutlined />
          <Text strong>{t('tasks.detail_section_resources')}</Text>
        </Space>
      }
      className="gaf-mb-lg"
    >
      <Descriptions column={1} size="small" styles={{ label: { width: 100 } }}>
        <Descriptions.Item label={t('tasks.detail_game_profile')}>
          {task?.game_profile_detail ? (
            <Tag color="cyan">{task.game_profile_detail.game_name}</Tag>
          ) : (
            <Text type="secondary">{t('tasks.detail_unbound')}</Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label={t('tasks.detail_game_account')}>
          <Text>
            {(task?.game_account_details?.length ?? 0) > 0
              ? task!.game_account_details!.map((acc) => `${acc.game_name_display} - ${acc.username}`).join(', ')
              : t('tasks.detail_unbound')}
          </Text>
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );

  /** Render timestamp information for creation and last update */
  const renderTimestampInfo = () => (
    <Card
      size="small"
      title={
        <Space>
          <ClockCircleOutlined />
          <Text strong>{t('tasks.detail_section_timestamps')}</Text>
        </Space>
      }
      className="gaf-mb-lg"
    >
      <Descriptions column={1} size="small" styles={{ label: { width: 100 } }}>
        <Descriptions.Item label={t('tasks.detail_created_at')}>
          {task?.created_at ? dayjs(task.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
        </Descriptions.Item>
        <Descriptions.Item label={t('tasks.detail_updated_at')}>
          {task?.updated_at ? dayjs(task.updated_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );

  /** Render pipeline definition in collapsible JSON format */
  const renderPipelineDefinition = () => {
    const hasDefinition = task?.task_definition && Object.keys(task.task_definition).length > 0;

    return (
      <Collapse
        ghost
        size="small"
        items={[
          {
            key: 'pipeline',
            label: (
              <Space>
                <CodeOutlined />
                <Text strong>{t('tasks.detail_section_pipeline')}</Text>
              </Space>
            ),
            children: hasDefinition ? (
              <pre
                className="gaf-p-md gaf-text-xs gaf-m-0"
                style={{ background: token.colorBgLayout, borderRadius: 4, overflow: 'auto', maxHeight: 300 }}
              >
                {JSON.stringify(task.task_definition, null, 2)}
              </pre>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('tasks.detail_no_pipeline')}
                style={{ padding: '20px 0' }}
              />
            ),
          },
        ]}
      />
    );
  };

  return (
    <Drawer
      placement="right"
      size={640}
      open={open}
      onClose={onClose}
      destroyOnHidden
      title={
        <Space>
          <Text strong className="gaf-text-md">
            {task?.name || t('tasks.detail_title')}
          </Text>
          {task && (
            <Tag color={task.is_enabled ? 'success' : 'default'}>
              {task.is_enabled ? t('tasks.detail_status_enabled') : t('tasks.detail_status_disabled')}
            </Tag>
          )}
        </Space>
      }
      extra={
        <Space>
          {onEdit && task && (
            <Button icon={<EditOutlined />} onClick={() => onEdit(task)}>
              {t('tasks.detail_edit')}
            </Button>
          )}
          {onExecute && task && (
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => onExecute(task)}>
              {t('tasks.detail_execute')}
            </Button>
          )}
          {onClone && task && (
            <Button icon={<CopyOutlined />} onClick={() => onClone(task)}>
              {t('tasks.detail_clone')}
            </Button>
          )}
        </Space>
      }
    >
      <div className="gaf-p-xl">
        {task ? (
          <>
            {renderBasicInfo()}
            {renderAssociatedResources()}
            {renderTimestampInfo()}
            {renderPipelineDefinition()}
          </>
        ) : (
          <Empty description={t('tasks.detail_select_task')} />
        )}
      </div>
    </Drawer>
  );
}

export default TaskDetailDrawer;
