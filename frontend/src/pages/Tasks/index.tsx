import { useEffect, useState, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Button, Tag, Space, Popconfirm, Input, Select, Tooltip, App, Skeleton, Typography } from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  EyeOutlined,
  CopyOutlined,
  SearchOutlined,
  PlusOutlined,
  DownloadOutlined,
  UploadOutlined,
  DeleteOutlined,
  EditOutlined,
  CheckCircleOutlined,
  StopOutlined,
  FormOutlined,
} from '@ant-design/icons';
import { useTaskStore, type FetchTasksParams } from '@/stores/useTaskStore';
import { createTask, deleteTask, cloneTask, bulkAction } from '@/api/tasks';
import { fetchResourcePacks } from '@/api/resources';
import TaskFormModal from './TaskFormModal';
import TaskDetailDrawer from '@/components/Task/TaskDetailDrawer';
import TaskVersionHistory from '@/components/Task/TaskVersionHistory';
import PageWrapper from '@/components/Common/PageWrapper';
import type { ColumnsType } from 'antd/es/table';
import type { Key } from 'antd/es/table/interface';
import type { Task, ResourcePack } from '@/types/models';
import { useTranslation } from '@/i18n';

interface TasksPageProps {
  category?: string;
}

const CATEGORY_KEY_MAP: Record<string, string> = {
  daily: 'tasks.category_daily',
  weekly: 'tasks.category_weekly',
  event: 'tasks.category_event',
  custom: 'tasks.category_custom',
};

const STATUS_COLOR_MAP: Record<string, string> = {
  true: 'success',
  false: 'default',
};

export function TasksPage({ category }: TasksPageProps) {
  const { tasks, total, loading, fetchTasks, executeTask, cancelTask } = useTaskStore();
  const { message } = App.useApp();
  const t = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [resourcePackFilter, setResourcePackFilter] = useState<number | undefined>();
  const [resourcePacks, setResourcePacks] = useState<ResourcePack[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [versionHistoryOpen, setVersionHistoryOpen] = useState(false);
  const [versionTaskId, setVersionTaskId] = useState<number>(0);
  const [versionTaskName, setVersionTaskName] = useState('');

  // Build category prefix list (localized) for filtering
  const categoryPrefixes = useMemo(() => {
    return Object.values(CATEGORY_KEY_MAP).map((k) => t(k));
  }, [t]);

  const resourcePackAbortRef = useRef<AbortController | null>(null);

  // Fetch tasks when filters change; resourcePackFilter is sent server-side
  // (backend TaskViewSet.filterset_fields includes resource_pack).
  useEffect(() => {
    const params: FetchTasksParams = {};
    if (resourcePackFilter) params.resource_pack = resourcePackFilter;
    fetchTasks(params);
  }, [fetchTasks, resourcePackFilter]);

  useEffect(() => {
    resourcePackAbortRef.current?.abort();
    const controller = new AbortController();
    resourcePackAbortRef.current = controller;
    fetchResourcePacks({ page: 1, page_size: 200, signal: controller.signal })
      .then((res) => {
        if (!controller.signal.aborted) {
          setResourcePacks(res.results || []);
        }
      })
      .catch(() => {
        /* resource packs are optional */
      });
    return () => {
      controller.abort();
    };
  }, []);

  const filteredTasks = useMemo(() => {
    let result = tasks;
    if (category) {
      const prefix = CATEGORY_KEY_MAP[category] ? t(CATEGORY_KEY_MAP[category]) : '';
      if (prefix) {
        result = result.filter((task) => task.name && task.name.startsWith(prefix));
      } else {
        result = result.filter((task) => !task.name || !categoryPrefixes.some((p) => task.name!.startsWith(p)));
      }
    }
    if (searchText) {
      const kw = searchText.toLowerCase();
      result = result.filter(
        (task) =>
          (task.name && task.name.toLowerCase().includes(kw)) ||
          (task.description && task.description.toLowerCase().includes(kw)),
      );
    }
    if (statusFilter) {
      result = result.filter((task) => String(task.is_enabled) === statusFilter);
    }
    if (typeFilter) {
      result = result.filter((task) => task.execution_mode === typeFilter);
    }
    if (resourcePackFilter) {
      result = result.filter((task) => {
        const rpId = (task as Record<string, unknown>).resource_pack as number | undefined;
        return rpId === resourcePackFilter;
      });
    }
    return result;
  }, [tasks, category, searchText, statusFilter, typeFilter, resourcePackFilter, t, categoryPrefixes]);

  const handleExecute = async (taskId: number) => {
    try {
      await executeTask(taskId);
      message.success(t('tasks.msg_execute_started'));
    } catch {
      message.error(t('tasks.msg_execute_failed'));
    }
  };

  const handleCancel = async (taskId: number) => {
    try {
      await cancelTask(taskId);
      message.success(t('tasks.msg_stopped'));
    } catch {
      message.error(t('tasks.msg_stop_failed'));
    }
  };

  const handleCreate = () => {
    setEditingTask(null);
    setModalOpen(true);
  };

  const handleEdit = (task: Task) => {
    setEditingTask(task);
    setModalOpen(true);
  };

  const navigate = useNavigate();
  const handleStepEditor = (task: Task) => {
    // Navigate to the full-page step editor (Editor.tsx). Complements
    // TaskFormModal which only edits task metadata; TaskEditorPage edits
    // task_definition.nodes with drag-sort, schema validation, and JSON preview.
    navigate(`/tasks/${task.id}/edit`);
  };

  const handleDetail = (task: Task) => {
    setSelectedTask(task);
    setDetailOpen(true);
  };

  const handleVersionHistory = (task: Task) => {
    setVersionTaskId(task.id);
    setVersionTaskName(task.name);
    setVersionHistoryOpen(true);
  };

  const handleClone = async (taskId: number) => {
    try {
      await cloneTask(taskId);
      message.success(t('tasks.msg_cloned'));
      fetchTasks();
    } catch {
      message.error(t('tasks.msg_clone_failed'));
    }
  };

  const handleModalClose = () => {
    setModalOpen(false);
    setEditingTask(null);
  };

  const handleModalSuccess = () => {
    handleModalClose();
    fetchTasks();
  };

  const handleBatchDelete = async () => {
    if (selectedRowKeys.length === 0) return;
    try {
      const ids = selectedRowKeys.map(Number);
      await bulkAction({ action: 'delete', task_ids: ids });
      message.success(t('tasks.msg_deleted_count', { count: ids.length }));
      setSelectedRowKeys([]);
      fetchTasks();
    } catch {
      message.error(t('tasks.msg_batch_delete_failed'));
    }
  };

  const handleBatchEnable = async () => {
    if (selectedRowKeys.length === 0) return;
    try {
      const ids = selectedRowKeys.map(Number);
      await bulkAction({ action: 'enable', task_ids: ids });
      message.success(t('tasks.msg_enabled_count', { count: ids.length }));
      setSelectedRowKeys([]);
      fetchTasks();
    } catch {
      message.error(t('tasks.msg_batch_enable_failed'));
    }
  };

  const handleBatchDisable = async () => {
    if (selectedRowKeys.length === 0) return;
    try {
      const ids = selectedRowKeys.map(Number);
      await bulkAction({ action: 'disable', task_ids: ids });
      message.success(t('tasks.msg_disabled_count', { count: ids.length }));
      setSelectedRowKeys([]);
      fetchTasks();
    } catch {
      message.error(t('tasks.msg_batch_disable_failed'));
    }
  };

  const handleExport = () => {
    const selectedTasks = filteredTasks.filter((task) => selectedRowKeys.includes(task.id));
    if (selectedTasks.length === 0) {
      message.warning(t('tasks.msg_select_to_export'));
      return;
    }
    const exportData = selectedTasks.map(({ ...rest }) => rest);
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tasks_export_${Date.now()}.gaftask`;
    a.click();
    URL.revokeObjectURL(url);
    message.success(t('tasks.msg_exported_count', { count: selectedTasks.length }));
  };

  const handleImport = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const tasksData = JSON.parse(text) as Partial<Task>[];
      if (!Array.isArray(tasksData)) {
        message.error(t('tasks.msg_invalid_file'));
        return;
      }
      let imported = 0;
      for (const task of tasksData) {
        await createTask(task);
        imported++;
      }
      message.success(t('tasks.msg_imported_count', { count: imported }));
      fetchTasks();
    } catch {
      message.error(t('tasks.msg_import_failed'));
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: Key[]) => setSelectedRowKeys(keys),
  };

  const columns: ColumnsType<Task> = [
    {
      title: t('tasks.col_name'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
      render: (text: string) => (
        <Typography.Text strong ellipsis={{ tooltip: text }}>
          {text}
        </Typography.Text>
      ),
    },
    {
      title: t('tasks.col_description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      width: 300,
      render: (text: string) =>
        text ? (
          <Typography.Text type="secondary" ellipsis={{ tooltip: text }}>
            {text}
          </Typography.Text>
        ) : (
          '-'
        ),
    },
    {
      title: t('tasks.col_execution_mode'),
      dataIndex: 'execution_mode',
      key: 'execution_mode',
      width: 100,
      render: (mode: string) =>
        mode === 'pipeline'
          ? t('tasks.mode_pipeline')
          : mode === 'state_machine'
            ? t('tasks.mode_state_machine')
            : mode,
    },
    {
      title: t('tasks.col_game_accounts'),
      key: 'game_accounts',
      width: 200,
      ellipsis: true,
      render: (_: unknown, record: Task) => {
        const accounts = record.game_account_details || [];
        if (accounts.length === 0) return <Tag>{t('tasks.unbound')}</Tag>;
        return (
          <Space size={2} wrap>
            {accounts.slice(0, 2).map((a: { id: number; game_name_display: string; username: string }) => (
              <Tag key={a.id} color="blue">
                {a.username}
              </Tag>
            ))}
            {accounts.length > 2 && <Tag>+{accounts.length - 2}</Tag>}
          </Space>
        );
      },
    },
    {
      title: t('tasks.col_game_profile'),
      key: 'game_profile',
      width: 130,
      ellipsis: true,
      render: (_: unknown, record: Task) => {
        // R37-P1: prefer game_profile_detail.game_name; fallback to FK id; else unbound.
        if (record.game_profile_detail?.game_name) {
          return <Tag color="purple">{record.game_profile_detail.game_name}</Tag>;
        }
        if (record.game_profile) {
          return <Tag color="purple">#{record.game_profile}</Tag>;
        }
        return <Tag>{t('tasks.unbound')}</Tag>;
      },
    },
    {
      title: t('tasks.col_resource_pack'),
      key: 'resource_pack',
      width: 150,
      ellipsis: true,
      render: (_: unknown, record: Task) => {
        // N197-8: prefer resource_pack_detail; fallback to FK id; else unbound.
        const rp = (record as Record<string, unknown>).resource_pack_detail as
          { id: number; name: string; version: string; is_active: boolean } | undefined;
        if (rp?.name) {
          return (
            <Tag color={rp.is_active ? 'geekblue' : 'default'}>
              {rp.name} v{rp.version}
            </Tag>
          );
        }
        const rpId = (record as Record<string, unknown>).resource_pack as number | undefined;
        if (rpId) {
          return <Tag color="geekblue">#{rpId}</Tag>;
        }
        return <Tag>{t('tasks.unbound')}</Tag>;
      },
    },
    {
      title: t('tasks.col_status'),
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 100,
      render: (enabled: boolean) => (
        <Tag color={STATUS_COLOR_MAP[String(enabled)] || 'default'}>
          {enabled ? t('tasks.status_enabled') : t('tasks.status_disabled')}
        </Tag>
      ),
    },
    {
      title: t('tasks.col_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (val: string) => val || '-',
    },
    {
      title: t('tasks.col_action'),
      key: 'action',
      width: 380,
      render: (_, record) => (
        <div className="gaf-flex-center gaf-gap-xs">
          <Tooltip key="edit" title={t('tasks.action_edit')}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              aria-label={t('tasks.action_edit')}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Tooltip key="step-editor" title="步骤编辑器">
            <Button
              type="link"
              size="small"
              icon={<FormOutlined />}
              aria-label="步骤编辑器"
              onClick={() => handleStepEditor(record)}
            />
          </Tooltip>
          <Tooltip key="execute" title={t('tasks.action_execute')}>
            <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => handleExecute(record.id)}>
              {t('tasks.action_execute')}
            </Button>
          </Tooltip>
          <Tooltip key="stop" title={t('tasks.action_stop')}>
            <Button type="link" size="small" icon={<PauseCircleOutlined />} onClick={() => handleCancel(record.id)}>
              {t('tasks.action_stop')}
            </Button>
          </Tooltip>
          <Tooltip key="clone" title={t('tasks.action_clone')}>
            <Button
              type="link"
              size="small"
              icon={<CopyOutlined />}
              aria-label={t('tasks.action_clone')}
              onClick={() => handleClone(record.id)}
            />
          </Tooltip>
          <Button key="detail" type="link" size="small" icon={<EyeOutlined />} onClick={() => handleDetail(record)}>
            {t('tasks.action_detail')}
          </Button>
          <Button key="version" type="link" size="small" onClick={() => handleVersionHistory(record)}>
            {t('tasks.action_version')}
          </Button>
          <Popconfirm
            key="delete"
            title={t('tasks.confirm_delete')}
            onConfirm={async () => {
              try {
                await deleteTask(record.id);
                message.success(t('tasks.msg_deleted'));
                fetchTasks();
              } catch {
                message.error(t('tasks.msg_delete_failed'));
              }
            }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />} aria-label={t('tasks.action_delete')} />
          </Popconfirm>
        </div>
      ),
    },
  ];

  const typeOptions = useMemo(() => {
    const types = new Set(tasks.map((task) => task.execution_mode).filter(Boolean));
    return Array.from(types).map((mode) => ({
      label:
        mode === 'pipeline'
          ? t('tasks.mode_pipeline')
          : mode === 'state_machine'
            ? t('tasks.mode_state_machine')
            : mode,
      value: mode,
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks, t]);

  return (
    <PageWrapper
      title={t('tasks.page_title')}
      extra={
        <Space wrap>
          <Input.Search
            placeholder={t('tasks.search_placeholder')}
            allowClear
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={(v) => setSearchText(v)}
            className="gaf-w-md"
            prefix={<SearchOutlined />}
          />
          <Select
            placeholder={t('tasks.filter_status')}
            allowClear
            value={statusFilter}
            onChange={setStatusFilter}
            className="gaf-w-sm"
            options={[
              { label: t('tasks.status_enabled'), value: 'true' },
              { label: t('tasks.status_disabled'), value: 'false' },
            ]}
          />
          <Select
            placeholder={t('tasks.filter_mode')}
            allowClear
            value={typeFilter}
            onChange={setTypeFilter}
            style={{ width: 130 }}
            options={typeOptions}
          />
          <Select
            placeholder={t('tasks.col_resource_pack')}
            allowClear
            value={resourcePackFilter}
            onChange={(val) => setResourcePackFilter(val ?? undefined)}
            style={{ width: 160 }}
            options={resourcePacks.map((rp) => ({
              label: `${rp.name} v${rp.version}`,
              value: rp.id,
            }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            {t('tasks.btn_new')}
          </Button>
          <Button icon={<UploadOutlined />} onClick={handleImport}>
            {t('tasks.btn_import')}
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport} disabled={selectedRowKeys.length === 0}>
            {t('tasks.btn_export')}
          </Button>
        </Space>
      }
    >
      {selectedRowKeys.length > 0 && (
        <div className="gaf-flex gaf-gap-sm gaf-mb-md">
          <Button
            size="small"
            icon={
              <span aria-hidden="true">
                <CheckCircleOutlined />
              </span>
            }
            onClick={handleBatchEnable}
            type="primary"
            ghost
          >
            {t('tasks.btn_batch_enable', { count: selectedRowKeys.length })}
          </Button>
          <Button size="small" icon={<StopOutlined />} onClick={handleBatchDisable}>
            {t('tasks.btn_batch_disable', { count: selectedRowKeys.length })}
          </Button>
          <Button
            size="small"
            danger
            icon={
              <span aria-hidden="true">
                <DeleteOutlined />
              </span>
            }
            onClick={handleBatchDelete}
          >
            {t('tasks.btn_batch_delete', { count: selectedRowKeys.length })}
          </Button>
        </div>
      )}
      <input
        type="file"
        ref={fileInputRef}
        className="gaf-hidden"
        accept=".gaftask,.json"
        onChange={handleFileChange}
      />
      {loading ? (
        <Skeleton active title={false} paragraph={{ rows: 10 }} />
      ) : (
        <Table
          columns={columns}
          dataSource={filteredTasks || []}
          rowKey="id"
          rowSelection={rowSelection}
          scroll={{ x: 'max-content' }}
          pagination={{
            total,
            pageSize: 20,
            showTotal: (total) => t('tasks.total_count', { count: total }),
            onChange: (page) => {
              const params: FetchTasksParams = { page };
              if (resourcePackFilter) params.resource_pack = resourcePackFilter;
              fetchTasks(params);
            },
          }}
        />
      )}
      <TaskFormModal
        open={modalOpen}
        editingTask={editingTask}
        onClose={handleModalClose}
        onSuccess={handleModalSuccess}
      />
      <TaskDetailDrawer
        open={detailOpen}
        task={selectedTask}
        onClose={() => setDetailOpen(false)}
        onEdit={(task) => {
          setDetailOpen(false);
          handleEdit(task);
        }}
        onExecute={(task) => handleExecute(task.id)}
        onClone={(task) => {
          setDetailOpen(false);
          handleClone(task.id);
        }}
      />
      <TaskVersionHistory
        open={versionHistoryOpen}
        taskId={versionTaskId}
        taskName={versionTaskName}
        onClose={() => setVersionHistoryOpen(false)}
      />
    </PageWrapper>
  );
}

export default TasksPage;
