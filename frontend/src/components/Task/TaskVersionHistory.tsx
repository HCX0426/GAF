/**
 * Task Version History Modal component
 * Displays version snapshots for a specific task with rollback capability
 */
import { useEffect, useState } from 'react';
import { Modal, Table, Tag, Button, Space, Typography, Empty, Spin, App, Timeline, theme as antTheme } from 'antd';
import { HistoryOutlined, SaveOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { fetchTaskVersions, saveTaskVersion } from '@/api/misc';
import { useTranslation } from '@/i18n';

/** Task version item returned from the API */
interface TaskVersionItem {
  id: number;
  task: number;
  version_number: number;
  snapshot: Record<string, unknown>;
  change_description: string;
  created_by: number | null;
  created_by_username: string | null;
  created_at: string;
  snapshot_summary: string | null;
}

interface TaskVersionHistoryProps {
  open: boolean;
  taskId: number;
  taskName: string;
  onClose: () => void;
}

export function TaskVersionHistory({ open, taskId, taskName, onClose }: TaskVersionHistoryProps) {
  const { token } = antTheme.useToken();
  const { message } = App.useApp();
  const t = useTranslation();
  const [versions, setVersions] = useState<TaskVersionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && taskId) {
      loadVersions();
    }
  }, [open, taskId]);

  /** Load version list for the current task */
  async function loadVersions() {
    setLoading(true);
    try {
      const data = await fetchTaskVersions<{ versions?: TaskVersionItem[] }>(taskId);
      setVersions(data.versions || []);
    } catch {
      message.error(t('taskStudio.version_load_failed'));
    } finally {
      setLoading(false);
    }
  }

  /** Save current task configuration as a new version snapshot */
  async function handleSaveVersion() {
    setSaving(true);
    try {
      const data = await saveTaskVersion<{ message?: string; version_number?: number }>(taskId, '');
      message.success(data.message || t('taskStudio.version_saved', { version: data.version_number }));
      await loadVersions();
    } catch (err: unknown) {
      const errData = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      message.error(errData?.detail || t('taskStudio.version_save_failed'));
    } finally {
      setSaving(false);
    }
  }

  const columns = [
    {
      title: '版本号',
      dataIndex: 'version_number',
      key: 'version_number',
      width: 80,
      render: (v: number) => <Tag color="blue">v{v}</Tag>,
    },
    {
      title: '变更描述',
      dataIndex: 'change_description',
      key: 'change_description',
      ellipsis: true,
      render: (desc: string) => desc || <Typography.Text type="secondary">-</Typography.Text>,
    },
    {
      title: '创建者',
      dataIndex: 'created_by_username',
      key: 'created_by_username',
      width: 100,
      render: (name: string) => name || <Typography.Text type="secondary">系统</Typography.Text>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (ts: string) => new Date(ts).toLocaleString(),
    },
    {
      title: '快照摘要',
      dataIndex: 'snapshot_summary',
      key: 'snapshot_summary',
      ellipsis: true,
      render: (summary: string) => (
        <Typography.Text className="gaf-text-xs" type="secondary">
          {summary || '-'}
        </Typography.Text>
      ),
    },
  ];

  return (
    <Modal
      title={
        <Space>
          <HistoryOutlined />
          <span>版本历史 — {taskName}</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={800}
      footer={[
        <Button key="close" onClick={onClose}>
          关闭
        </Button>,
        <Button key="save" type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSaveVersion}>
          保存当前版本
        </Button>,
      ]}
    >
      <Spin spinning={loading}>
        {versions.length > 0 ? (
          <>
            <Table
              dataSource={versions}
              columns={columns}
              rowKey="id"
              pagination={false}
              size="small"
              scroll={{ y: 300 }}
            />
            <div className="gaf-mt-md">
              <Timeline
                items={versions.slice(0, 5).map((v) => ({
                  color: v.version_number === versions[0].version_number ? 'green' : 'gray',
                  content: (
                    <Space>
                      <Tag>v{v.version_number}</Tag>
                      <span>{v.change_description || '无描述'}</span>
                      <ClockCircleOutlined className="gaf-text-xs" style={{ color: token.colorTextTertiary }} />
                      <span className="gaf-text-xs" style={{ color: token.colorTextTertiary }}>
                        {new Date(v.created_at).toLocaleString()}
                      </span>
                    </Space>
                  ),
                }))}
              />
            </div>
          </>
        ) : (
          <Empty
            description="暂无版本记录，点击「保存当前版本」创建第一个版本快照"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSaveVersion}>
              保存当前版本
            </Button>
          </Empty>
        )}
      </Spin>
    </Modal>
  );
}

export default TaskVersionHistory;
