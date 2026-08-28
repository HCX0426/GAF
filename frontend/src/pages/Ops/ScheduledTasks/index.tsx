/**
 * fixed when task management page
 * supports list view and FullCalendar calendar view switch
 * supports fixed when task CRUD, enable / disable, delete
 * supports execute history to compare feature
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table,
  Tag,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  Space,
  Popconfirm,
  Radio,
  Popover,
  Card,
  App,
  Tabs,
  Spin,
  Empty,
  Typography,
  Badge,
  theme,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  UnorderedListOutlined,
  CalendarOutlined,
  HistoryOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DiffOutlined,
  BranchesOutlined,
  EditOutlined,
} from '@ant-design/icons';
import { fetchScheduledTasks, createScheduledTask, deleteScheduledTask, toggleScheduledTask } from '@/api/scheduler';
import { fetchTasks, compareExecutions } from '@/api/tasks';
import { fetchTaskChains, deleteTaskChain, createTaskChain } from '@/api/tasks';
import type { TaskChain } from '@/types/models';
import CronExpressionEditor from '@/components/Editor/CronExpressionEditor';
import PageWrapper from '@/components/Common/PageWrapper';
import type { ColumnsType } from 'antd/es/table';
import type { ScheduledTask, ScheduleType, CreateScheduledTaskRequest, Task } from '@/types/models';
import type { EventClickArg, EventDropArg } from '@fullcalendar/core';
import type { DateClickArg } from '@fullcalendar/interaction';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';
import dayjs from 'dayjs';
import { fetchSchedulerExecutions } from '@/api/scheduler';
import { useTranslation, getLocale } from '@/i18n';

/** Schedule type i18n key mapping */
const SCHEDULE_TYPE_LABEL_KEY: Record<ScheduleType, string> = {
  periodic: 'scheduledTasks.schedule_type.periodic',
  one_time: 'scheduledTasks.schedule_type.one_time',
};

/** FullCalendar locale mapping from app locale */
const FULLCALENDAR_LOCALE_MAP: Record<string, string> = {
  'zh-CN': 'zh-cn',
  'en-US': 'en',
  'ja-JP': 'ja',
  'ko-KR': 'ko',
};

/** task type color mapping */
const TASK_TYPE_COLORS: Record<string, string> = {
  daily: '#1890ff',
  weekly: '#52c41a',
  event: '#fa8d14',
  custom: '#722ed1',
};

/** view mode type */
type ViewMode = 'list' | 'calendar';

/** Execution history record interface */
interface ExecutionRecord {
  id: string;
  task_name: string;
  scheduled_task_id: string;
  status: 'success' | 'failed' | 'timeout' | 'running';
  started_at: string;
  finished_at?: string;
  duration_seconds?: number;
  error_message?: string;
}

/** Diff result item interface */
interface DiffItem {
  field: string;
  baseValue: string;
  compareValue: string;
  changeType: 'added' | 'removed' | 'modified';
}

/** fixed when task management page component */
export function ScheduledTasksPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const t = useTranslation();
  const { token } = theme.useToken();
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [availableTasks, setAvailableTasks] = useState<Task[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [popoverTask, setPopoverTask] = useState<ScheduledTask | null>(null);
  const [activeTab, setActiveTab] = useState('tasks');
  const [taskChains, setTaskChains] = useState<TaskChain[]>([]);
  const [chainLoading, setChainLoading] = useState(false);
  const [execHistory, setExecHistory] = useState<ExecutionRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  /** execute to compare related status */
  const [comparingExecution, setComparingExecution] = useState<string | null>(null);
  const [compareModalOpen, setCompareModalOpen] = useState(false);
  const [otherExecutionId, setOtherExecutionId] = useState<string>('');
  const [diffResult, setDiffResult] = useState<DiffItem[] | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);

  const [form] = Form.useForm();
  const scheduleType = Form.useWatch('schedule_type', form);

  /** AbortController refs for cancelling in-flight requests */
  const tasksAbortRef = useRef<AbortController | null>(null);
  const availableTasksAbortRef = useRef<AbortController | null>(null);
  const historyAbortRef = useRef<AbortController | null>(null);
  const chainsAbortRef = useRef<AbortController | null>(null);

  /** load fixed when task list */
  const loadScheduledTasks = useCallback(async () => {
    tasksAbortRef.current?.abort();
    const controller = new AbortController();
    tasksAbortRef.current = controller;

    setLoading(true);
    try {
      const res = await fetchScheduledTasks({ page, page_size: 50, signal: controller.signal });
      if (!controller.signal.aborted) {
        setTasks(res.results || []);
        setTotal(res.count);
      }
    } catch {
      // load failed
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [page]);

  /** load available task list ( used for create new Modal) */
  const loadAvailableTasks = async () => {
    availableTasksAbortRef.current?.abort();
    const controller = new AbortController();
    availableTasksAbortRef.current = controller;

    try {
      const res = await fetchTasks({ page: 1, page_size: 100, signal: controller.signal });
      if (!controller.signal.aborted) {
        setAvailableTasks(res.results || []);
      }
    } catch {
      // load failed
    }
  };

  /** Load execution history for scheduled tasks */
  const loadExecutionHistory = useCallback(async () => {
    historyAbortRef.current?.abort();
    const controller = new AbortController();
    historyAbortRef.current = controller;

    setHistoryLoading(true);
    try {
      const data = (await fetchSchedulerExecutions({ page_size: 50, signal: controller.signal })) as
        { results?: ExecutionRecord[] } | ExecutionRecord[];
      if (!controller.signal.aborted) {
        setExecHistory((data as { results?: ExecutionRecord[] }).results || (data as ExecutionRecord[]) || []);
      }
    } catch {
      setExecHistory([]);
    } finally {
      if (!controller.signal.aborted) {
        setHistoryLoading(false);
      }
    }
  }, []);

  /** Load task chain list */
  const loadTaskChains = useCallback(async () => {
    chainsAbortRef.current?.abort();
    const controller = new AbortController();
    chainsAbortRef.current = controller;

    setChainLoading(true);
    try {
      const res = await fetchTaskChains({ page: 1, page_size: 100, signal: controller.signal });
      if (!controller.signal.aborted) {
        setTaskChains(res.results || []);
      }
    } catch {
      // ignore
    } finally {
      if (!controller.signal.aborted) {
        setChainLoading(false);
      }
    }
  }, []);

  /** Load chains when switching to chain tab */
  useEffect(() => {
    if (activeTab === 'chains' && taskChains.length === 0) {
      loadTaskChains();
    }
    return () => {
      chainsAbortRef.current?.abort();
      chainsAbortRef.current = null;
    };
  }, [activeTab, taskChains.length, loadTaskChains]);

  /** Load history when switching to history tab */
  useEffect(() => {
    if (activeTab === 'history' && execHistory.length === 0) {
      loadExecutionHistory();
    }
    return () => {
      historyAbortRef.current?.abort();
      historyAbortRef.current = null;
    };
  }, [activeTab, execHistory.length, loadExecutionHistory]);

  useEffect(() => {
    loadScheduledTasks();
    return () => {
      tasksAbortRef.current?.abort();
      tasksAbortRef.current = null;
    };
  }, [loadScheduledTasks]);

  /** open create new modal */
  const handleOpenModal = () => {
    loadAvailableTasks();
    form.resetFields();
    form.setFieldsValue({ schedule_type: 'periodic', is_enabled: true });
    setModalOpen(true);
  };

  /** submit create new scheduled when task */
  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreating(true);
      const data: CreateScheduledTaskRequest = {
        task: values.task,
        schedule_type: values.schedule_type,
        is_enabled: values.is_enabled ?? true,
      };
      if (values.schedule_type === 'periodic') {
        data.cron_expression = values.cron_expression;
      } else if (values.schedule_type === 'one_time') {
        data.scheduled_time = values.scheduled_time?.toISOString();
      }
      await createScheduledTask(data);
      message.success(t('scheduledTasks.message.create_success'));
      setModalOpen(false);
      loadScheduledTasks();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string; [key: string]: unknown } }; message?: string };
      const data = axiosErr?.response?.data;
      const detail = (data as Record<string, unknown>)?.detail as string | undefined;
      const fieldErrors =
        data && typeof data === 'object'
          ? Object.entries(data)
              .filter(([key]) => key !== 'detail' && Array.isArray((data as Record<string, unknown>)[key]))
              .map(([key, msgs]) => `${key}: ${(msgs as string[]).join(', ')}`)
              .join('\n')
          : '';
      // F10 fix (2026-08-28): JSON.stringify(undefined) 返回 undefined（非字符串），再 .slice 崩溃。
      // 用 String() 兜底任何非字符串输入（校验错误/axios 错误均安全）。
      const errMsg = axiosErr instanceof Error ? axiosErr.message : String(data ?? '').slice(0, 200);
      console.error('[ScheduledTasks] create failed:', { err, data, fieldErrors });
      if (detail) {
        message.error(`${t('scheduledTasks.message.create_failed')}: ${detail}`);
      } else if (fieldErrors) {
        message.error(`${t('scheduledTasks.message.create_failed')}: ${fieldErrors.split('\n')[0]}`);
      } else {
        message.error(
          `${t('scheduledTasks.message.create_failed')}: ${errMsg || t('scheduledTasks.message.unknown_error')}`,
        );
      }
    } finally {
      setCreating(false);
    }
  };

  /** switch enable / disable */
  const handleToggle = async (id: number, enabled: boolean) => {
    try {
      await toggleScheduledTask(id);
      message.success(
        enabled ? t('scheduledTasks.message.toggle_disabled') : t('scheduledTasks.message.toggle_enabled'),
      );
      loadScheduledTasks();
    } catch {
      message.error(t('scheduledTasks.message.action_failed'));
    }
  };

  /** delete fixed when task */
  const handleDelete = async (id: number) => {
    try {
      await deleteScheduledTask(id);
      message.success(t('scheduledTasks.message.deleted'));
      loadScheduledTasks();
    } catch {
      message.error(t('scheduledTasks.message.delete_failed'));
    }
  };

  /** delete task chain */
  const handleDeleteChain = async (chainId: number) => {
    try {
      await deleteTaskChain(chainId);
      message.success(t('scheduledTasks.message.chain_deleted'));
      loadTaskChains();
    } catch {
      message.error(t('scheduledTasks.message.delete_failed'));
    }
  };

  /** open DAG editor edit existing task chain */
  const handleEditChain = (chainId: number) => {
    navigate(`/ops/scheduler/dag/${chainId}`);
  };

  /** create new task chain and navigate edit */
  const handleCreateChain = async () => {
    try {
      const chain = await createTaskChain({
        name: t('scheduledTasks.chain.default_name'),
        dag_data: { nodes: [], edges: [] },
        is_enabled: true,
      });
      message.success(t('scheduledTasks.message.chain_created'));
      navigate(`/ops/scheduler/dag/${chain.id}`);
    } catch {
      message.error(t('scheduledTasks.message.create_failed'));
    }
  };

  /** open execute to compare modal */
  const handleOpenCompare = (executionId: string) => {
    setComparingExecution(executionId);
    setOtherExecutionId('');
    setDiffResult(null);
    setCompareModalOpen(true);
  };

  /** execute to compare request */
  const handleCompare = async () => {
    if (!comparingExecution || !otherExecutionId) {
      message.warning(t('scheduledTasks.message.compare_select_required'));
      return;
    }
    setDiffLoading(true);
    try {
      const result = await compareExecutions(Number(comparingExecution), Number(otherExecutionId));
      const diffs: DiffItem[] = (result.diffs as DiffItem[]) || [];
      setDiffResult(diffs);
    } catch {
      message.error(t('scheduledTasks.message.compare_failed'));
      setDiffResult(null);
    } finally {
      setDiffLoading(false);
    }
  };

  /** get to compare diff color label */
  const getDiffTagColor = (changeType: string) => {
    if (changeType === 'added') return 'green';
    if (changeType === 'removed') return 'red';
    return 'orange';
  };

  /** get to compare diff local transform description */
  const getDiffLabel = (changeType: string) => {
    if (changeType === 'added') return t('scheduledTasks.diff.added');
    if (changeType === 'removed') return t('scheduledTasks.diff.removed');
    return t('scheduledTasks.diff.modified');
  };

  /** convert is FullCalendar event format */
  const calendarEvents = (tasks || [])
    .filter((tTask) => tTask.last_executed_at || tTask.cron_expression)
    .map((task) => ({
      id: task.id,
      title: t('scheduledTasks.popover.calendar_event_title', { id: task.task }),
      start: task.last_executed_at || task.created_at,
      end: task.last_executed_at ? dayjs(task.last_executed_at).add(1, 'hour').toISOString() : undefined,
      backgroundColor:
        TASK_TYPE_COLORS[task.schedule_type === 'periodic' ? 'daily' : 'custom'] || TASK_TYPE_COLORS.custom,
      borderColor: 'transparent',
      extendedProps: { task },
    }));

  /** calendar click event */
  const handleEventClick = (info: EventClickArg) => {
    const task = info.event.extendedProps.task as ScheduledTask;
    setPopoverTask(task);
  };

  /** calendar date click */
  const handleDateClick = (info: DateClickArg) => {
    form.resetFields();
    form.setFieldsValue({
      schedule_type: 'one_time',
      run_at: dayjs(info.date).format('YYYY-MM-DDTHH:mm'),
      enabled: true,
    });
    loadAvailableTasks();
    setModalOpen(true);
  };

  /** drag event */
  const handleEventDrop = async (info: EventDropArg) => {
    const task = info.event.extendedProps.task as ScheduledTask;
    const newTime = info.event.start;
    if (!newTime || !task) return;
    try {
      message.info(
        t('scheduledTasks.message.time_adjusted', {
          name: (task as ScheduledTask & { name?: string }).name || `#${task.id}`,
        }),
      );
      loadScheduledTasks();
    } catch {
      message.error(t('scheduledTasks.message.adjust_failed'));
      info.revert();
    }
  };

  /** fixed when task list column config */
  const columns: ColumnsType<ScheduledTask> = [
    {
      title: t('scheduledTasks.column.task_id'),
      dataIndex: 'task',
      key: 'task',
      width: 100,
    },
    {
      title: t('scheduledTasks.column.schedule_type'),
      dataIndex: 'schedule_type',
      key: 'schedule_type',
      width: 120,
      render: (val: string) => {
        if (val === 'periodic') return <Tag color="blue">{t('scheduledTasks.tag.periodic')}</Tag>;
        return <Tag>{t('scheduledTasks.tag.one_time')}</Tag>;
      },
    },
    {
      title: t('scheduledTasks.column.cron_expression'),
      dataIndex: 'cron_expression',
      key: 'cron_expression',
      width: 140,
      render: (val: string | null) => val || '-',
    },
    {
      title: t('scheduledTasks.column.enabled'),
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 100,
      render: (isEnabled: boolean, record) => (
        <Switch checked={isEnabled} onChange={(val) => handleToggle(record.id, val)} size="small" />
      ),
    },
    {
      title: t('scheduledTasks.column.last_executed'),
      dataIndex: 'last_executed_at',
      key: 'last_executed_at',
      width: 180,
      render: (val: string | null) => (val ? dayjs(val).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: t('scheduledTasks.column.action'),
      key: 'action',
      width: 80,
      render: (_, record) => (
        <Popconfirm title={t('scheduledTasks.confirm.delete_task')} onConfirm={() => handleDelete(record.id)}>
          <Button type="link" danger icon={<DeleteOutlined />} size="small">
            {t('scheduledTasks.button.delete')}
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <PageWrapper
      title={t('scheduledTasks.page.title')}
      extra={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              loadScheduledTasks();
              if (activeTab === 'history') loadExecutionHistory();
              if (activeTab === 'chains') loadTaskChains();
            }}
          >
            {t('scheduledTasks.button.refresh')}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenModal}>
            {t('scheduledTasks.button.create')}
          </Button>
          <Button icon={<BranchesOutlined />} onClick={() => navigate('/ops/scheduler/dag')}>
            {t('scheduledTasks.button.dag_editor')}
          </Button>
        </Space>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'tasks',
            label: (
              <span>
                <UnorderedListOutlined /> {t('scheduledTasks.tab.tasks')}
              </span>
            ),
            children: (
              <div>
                <div className="gaf-mb-lg">
                  <Radio.Group
                    value={viewMode}
                    onChange={(e) => setViewMode(e.target.value)}
                    size="small"
                    optionType="button"
                    buttonStyle="solid"
                  >
                    <Radio.Button value="list">
                      <UnorderedListOutlined /> {t('scheduledTasks.view.list')}
                    </Radio.Button>
                    <Radio.Button value="calendar">
                      <CalendarOutlined /> {t('scheduledTasks.view.calendar')}
                    </Radio.Button>
                  </Radio.Group>
                </div>

                {viewMode === 'list' ? (
                  <Table
                    columns={columns}
                    dataSource={tasks || []}
                    rowKey="id"
                    loading={loading}
                    scroll={{ x: 'max-content' }}
                    pagination={{
                      total,
                      current: page,
                      pageSize: 20,
                      showTotal: (totalCount) => t('scheduledTasks.pagination.total', { count: totalCount }),
                      onChange: (p) => setPage(p),
                    }}
                  />
                ) : (
                  <Card>
                    <div className="gaf-position-relative">
                      <Popover
                        content={
                          popoverTask ? (
                            <div style={{ minWidth: 200 }}>
                              <p>
                                <strong>{t('scheduledTasks.popover.task_label', { id: popoverTask.task })}</strong>
                              </p>
                              <p>
                                {t('scheduledTasks.popover.type')}
                                {popoverTask.cron_expression
                                  ? t('scheduledTasks.tag.periodic')
                                  : t('scheduledTasks.tag.one_time')}
                              </p>
                              {popoverTask.cron_expression && (
                                <p>
                                  {t('scheduledTasks.popover.cron')}
                                  {popoverTask.cron_expression}
                                </p>
                              )}
                              {popoverTask.scheduled_time && (
                                <p>
                                  {t('scheduledTasks.popover.run_time')}
                                  {dayjs(popoverTask.scheduled_time).format('YYYY-MM-DD HH:mm')}
                                </p>
                              )}
                              <p>
                                {t('scheduledTasks.popover.status')}
                                {popoverTask.is_enabled ? (
                                  <Tag color="green">{t('scheduledTasks.tag.enabled')}</Tag>
                                ) : (
                                  <Tag color="red">{t('scheduledTasks.tag.disabled')}</Tag>
                                )}
                              </p>
                              {popoverTask.last_executed_at && (
                                <p>
                                  {t('scheduledTasks.popover.last_executed')}
                                  {dayjs(popoverTask.last_executed_at).format('MM-DD HH:mm')}
                                </p>
                              )}
                              <Space className="gaf-mt-sm">
                                <Switch
                                  checked={popoverTask.is_enabled}
                                  onChange={(val) => handleToggle(popoverTask.id, val)}
                                  size="small"
                                />
                                <Popconfirm
                                  title={t('scheduledTasks.confirm.delete_short')}
                                  onConfirm={() => handleDelete(popoverTask.id)}
                                >
                                  <Button size="small" danger>
                                    {t('scheduledTasks.button.delete')}
                                  </Button>
                                </Popconfirm>
                              </Space>
                            </div>
                          ) : null
                        }
                        title={t('scheduledTasks.popover.title')}
                        open={!!popoverTask}
                        onOpenChange={(open) => {
                          if (!open) setPopoverTask(null);
                        }}
                        trigger="click"
                      >
                        <div />
                      </Popover>
                      {/* @ts-expect-error FullCalendar 6.x JSX type incompatible with React 18 strict mode */}
                      <FullCalendar
                        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
                        initialView="dayGridMonth"
                        headerToolbar={{
                          left: 'prev,next today',
                          center: 'title',
                          right: 'dayGridMonth,timeGridWeek,timeGridDay',
                        }}
                        events={calendarEvents}
                        editable={true}
                        selectable={true}
                        eventClick={handleEventClick}
                        dateClick={handleDateClick}
                        eventDrop={handleEventDrop}
                        locale={FULLCALENDAR_LOCALE_MAP[getLocale()] || 'en'}
                        height="auto"
                        dayMaxEvents={3}
                      />
                    </div>
                  </Card>
                )}
              </div>
            ),
          },
          {
            key: 'history',
            label: (
              <span>
                <HistoryOutlined /> {t('scheduledTasks.tab.history')}
                {execHistory.length > 0 && <Badge count={execHistory.length} className="gaf-ml-sm" />}
              </span>
            ),
            children: (
              <Spin spinning={historyLoading}>
                {execHistory.length === 0 && !historyLoading ? (
                  <Empty description={t('scheduledTasks.empty.history')} />
                ) : (
                  <Table
                    dataSource={execHistory}
                    rowKey="id"
                    pagination={{
                      pageSize: 15,
                      showTotal: (totalCount) => t('scheduledTasks.pagination.total_records', { count: totalCount }),
                    }}
                    size="small"
                    columns={[
                      {
                        title: t('scheduledTasks.column.task_name'),
                        dataIndex: 'task_name',
                        key: 'task_name',
                        ellipsis: true,
                      },
                      {
                        title: t('scheduledTasks.column.status'),
                        dataIndex: 'status',
                        key: 'status',
                        width: 100,
                        render: (status: string) => {
                          if (status === 'success')
                            return (
                              <Tag color="success" icon={<CheckCircleOutlined />}>
                                {t('scheduledTasks.tag.success')}
                              </Tag>
                            );
                          if (status === 'failed')
                            return (
                              <Tag color="error" icon={<CloseCircleOutlined />}>
                                {t('scheduledTasks.tag.failed')}
                              </Tag>
                            );
                          if (status === 'timeout')
                            return (
                              <Tag color="warning" icon={<ClockCircleOutlined />}>
                                {t('scheduledTasks.tag.timeout')}
                              </Tag>
                            );
                          return (
                            <Tag color="processing" icon={<ClockCircleOutlined />}>
                              {t('scheduledTasks.tag.running')}
                            </Tag>
                          );
                        },
                      },
                      {
                        title: t('scheduledTasks.column.started_at'),
                        dataIndex: 'started_at',
                        key: 'started_at',
                        width: 180,
                        render: (val: string) => (val ? dayjs(val).format('YYYY-MM-DD HH:mm:ss') : '-'),
                      },
                      {
                        title: t('scheduledTasks.column.finished_at'),
                        dataIndex: 'finished_at',
                        key: 'finished_at',
                        width: 180,
                        render: (val: string | null) => (val ? dayjs(val).format('YYYY-MM-DD HH:mm:ss') : '-'),
                      },
                      {
                        title: t('scheduledTasks.column.duration'),
                        dataIndex: 'duration_seconds',
                        key: 'duration_seconds',
                        width: 90,
                        render: (val: number | null) => (val !== null && val !== undefined ? `${val}s` : '-'),
                      },
                      {
                        title: t('scheduledTasks.column.error_message'),
                        dataIndex: 'error_message',
                        key: 'error_message',
                        ellipsis: true,
                        render: (val: string | null) => val || '-',
                      },
                      {
                        title: t('scheduledTasks.column.action'),
                        key: 'action',
                        width: 100,
                        render: (_, record) => (
                          <Button
                            type="link"
                            size="small"
                            icon={<DiffOutlined />}
                            onClick={() => handleOpenCompare(record.id)}
                          >
                            {t('scheduledTasks.button.compare')}
                          </Button>
                        ),
                      },
                    ]}
                  />
                )}
              </Spin>
            ),
          },
          {
            key: 'chains',
            label: (
              <span>
                <BranchesOutlined /> {t('scheduledTasks.tab.chains')}
                {taskChains.length > 0 && <Badge count={taskChains.length} className="gaf-ml-sm" />}
              </span>
            ),
            children: (
              <div>
                <div className="gaf-mb-lg gaf-flex" style={{ justifyContent: 'flex-end' }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateChain}>
                    {t('scheduledTasks.button.create_chain')}
                  </Button>
                </div>
                <Table
                  columns={[
                    { title: t('scheduledTasks.column.name'), dataIndex: 'name', key: 'name', ellipsis: true },
                    {
                      title: t('scheduledTasks.column.description'),
                      dataIndex: 'description',
                      key: 'description',
                      ellipsis: true,
                    },
                    {
                      title: t('scheduledTasks.column.node_count'),
                      dataIndex: 'node_count',
                      key: 'node_count',
                      width: 80,
                      render: (v: number) => v || 0,
                    },
                    {
                      title: t('scheduledTasks.column.status'),
                      dataIndex: 'is_enabled',
                      key: 'is_enabled',
                      width: 80,
                      render: (v: boolean) => (
                        <Tag color={v ? 'green' : 'default'}>
                          {v ? t('scheduledTasks.tag.enabled') : t('scheduledTasks.tag.disabled')}
                        </Tag>
                      ),
                    },
                    {
                      title: t('scheduledTasks.column.created_by'),
                      dataIndex: 'created_by_username',
                      key: 'created_by_username',
                      width: 100,
                    },
                    {
                      title: t('scheduledTasks.column.created_at'),
                      dataIndex: 'created_at',
                      key: 'created_at',
                      width: 180,
                      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
                    },
                    {
                      title: t('scheduledTasks.column.action'),
                      key: 'action',
                      width: 150,
                      render: (_: unknown, record: TaskChain) => (
                        <Space>
                          <Button
                            type="link"
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => handleEditChain(record.id)}
                          >
                            {t('scheduledTasks.button.edit')}
                          </Button>
                          <Popconfirm
                            title={t('scheduledTasks.confirm.delete_chain')}
                            onConfirm={() => handleDeleteChain(record.id)}
                          >
                            <Button type="link" danger size="small" icon={<DeleteOutlined />}>
                              {t('scheduledTasks.button.delete')}
                            </Button>
                          </Popconfirm>
                        </Space>
                      ),
                    },
                  ]}
                  dataSource={taskChains}
                  rowKey="id"
                  loading={chainLoading}
                  pagination={false}
                  locale={{ emptyText: t('scheduledTasks.empty.chains') }}
                />
              </div>
            ),
          },
        ]}
      />

      {/* 新建定时任务弹窗 */}
      <Modal
        title={t('scheduledTasks.modal.create_title')}
        open={modalOpen}
        onOk={handleCreate}
        onCancel={() => setModalOpen(false)}
        confirmLoading={creating}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label={t('scheduledTasks.form.task_name')}
            rules={[{ required: true, message: t('scheduledTasks.form.task_name_required') }]}
          >
            <Input placeholder={t('scheduledTasks.form.task_name_placeholder')} />
          </Form.Item>
          <Form.Item
            name="task"
            label={t('scheduledTasks.form.task')}
            rules={[{ required: true, message: t('scheduledTasks.form.task_required') }]}
          >
            <Select
              placeholder={t('scheduledTasks.form.task_placeholder')}
              options={availableTasks.map((tTask) => ({ label: tTask.name, value: tTask.id }))}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item
            name="schedule_type"
            label={t('scheduledTasks.form.schedule_type')}
            rules={[{ required: true, message: t('scheduledTasks.form.schedule_type_required') }]}
          >
            <Select
              options={Object.entries(SCHEDULE_TYPE_LABEL_KEY).map(([value, key]) => ({ value, label: t(key) }))}
            />
          </Form.Item>
          {scheduleType === 'periodic' && (
            <Form.Item
              name="cron_expression"
              label={t('scheduledTasks.form.cron_expression')}
              rules={[{ required: true, message: t('scheduledTasks.form.cron_expression_required') }]}
            >
              <CronExpressionEditor />
            </Form.Item>
          )}
          {scheduleType === 'one_time' && (
            <Form.Item
              name="run_at"
              label={t('scheduledTasks.form.run_at')}
              rules={[{ required: true, message: t('scheduledTasks.form.run_at_required') }]}
            >
              <Input type="datetime-local" />
            </Form.Item>
          )}
          <Form.Item name="is_enabled" label={t('scheduledTasks.form.enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 执行对比弹窗 */}
      <Modal
        title={t('scheduledTasks.modal.compare_title')}
        open={compareModalOpen}
        onCancel={() => setCompareModalOpen(false)}
        footer={null}
        width={900}
        destroyOnHidden
      >
        <div className="gaf-mb-lg">
          <Typography.Text type="secondary">
            {t('scheduledTasks.compare.base_execution', {
              name: (execHistory.find((e) => e.id === comparingExecution)?.task_name || comparingExecution) ?? '',
            })}
          </Typography.Text>
        </div>

        <Space className="gaf-mb-lg" align="start">
          <Select
            style={{ width: 300 }}
            placeholder={t('scheduledTasks.compare.placeholder')}
            value={otherExecutionId || undefined}
            onChange={(val) => setOtherExecutionId(val)}
            options={execHistory
              .filter((e) => e.id !== comparingExecution)
              .map((e) => ({
                label: `${e.task_name} (${dayjs(e.started_at).format('MM-DD HH:mm')})`,
                value: e.id,
              }))}
            showSearch
            optionFilterProp="label"
          />
          <Button
            type="primary"
            icon={<DiffOutlined />}
            onClick={handleCompare}
            loading={diffLoading}
            disabled={!otherExecutionId}
          >
            {t('scheduledTasks.button.compare')}
          </Button>
        </Space>

        {diffResult !== null && (
          <div className="gaf-overflow-auto" style={{ maxHeight: 500 }}>
            {diffResult.length === 0 ? (
              <Empty description={t('scheduledTasks.empty.diff_same')} />
            ) : (
              <div className="gaf-flex gaf-gap-lg">
                <div className="gaf-flex-1">
                  <Typography.Text strong>{t('scheduledTasks.compare.base_label')}</Typography.Text>
                  <div className="gaf-mt-sm">
                    {diffResult
                      .filter((item) => item.changeType === 'removed' || item.changeType === 'modified')
                      .map((item) => (
                        <div
                          key={`base-${item.field}`}
                          className="gaf-mb-xs gaf-py-sm gaf-px-md"
                          style={{
                            background: item.changeType === 'removed' ? token.colorErrorBg : token.colorWarningBg,
                            border: `1px solid ${item.changeType === 'removed' ? token.colorErrorBorder : token.colorWarningBorder}`,
                            borderRadius: 4,
                          }}
                        >
                          <Tag color={getDiffTagColor(item.changeType)}>{getDiffLabel(item.changeType)}</Tag>
                          <Typography.Text strong>{item.field}</Typography.Text>
                          <Typography.Text type="danger" delete className="gaf-ml-sm">
                            {String(item.baseValue)}
                          </Typography.Text>
                        </div>
                      ))}
                  </div>
                </div>
                <div className="gaf-flex-1">
                  <Typography.Text strong>{t('scheduledTasks.compare.compare_label')}</Typography.Text>
                  <div className="gaf-mt-sm">
                    {diffResult
                      .filter((item) => item.changeType === 'added' || item.changeType === 'modified')
                      .map((item) => (
                        <div
                          key={`cmp-${item.field}`}
                          className="gaf-mb-xs gaf-py-sm gaf-px-md"
                          style={{
                            background: item.changeType === 'added' ? token.colorSuccessBg : token.colorWarningBg,
                            border: `1px solid ${item.changeType === 'added' ? token.colorSuccessBorder : token.colorWarningBorder}`,
                            borderRadius: 4,
                          }}
                        >
                          <Tag color={getDiffTagColor(item.changeType)}>{getDiffLabel(item.changeType)}</Tag>
                          <Typography.Text strong>{item.field}</Typography.Text>
                          <Typography.Text type="success" className="gaf-ml-sm">
                            {String(item.compareValue)}
                          </Typography.Text>
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </PageWrapper>
  );
}

export default ScheduledTasksPage;
