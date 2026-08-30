/**
 * execute monitor page — Phase 3.2 added strong
 * task execute record list + step progress bar + manual intervention button + log end end
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Table,
  Tag,
  DatePicker,
  Select,
  Space,
  Button,
  Tabs,
  Input,
  Progress,
  Modal,
  App,
  Typography,
  Tooltip,
  Skeleton,
  theme as antTheme,
  Alert,
} from 'antd';
import {
  ReloadOutlined,
  DashboardOutlined,
  UnorderedListOutlined,
  EyeOutlined,
  PauseCircleOutlined,
  CaretRightOutlined,
  StepForwardOutlined,
  StopOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import {
  fetchAllExecutions,
  fetchExecutionSteps,
  pauseExecution,
  resumeExecution,
  cancelExecution,
  skipExecutionStep,
  failExecutionStep,
} from '@/api/executions';
import type { ColumnsType } from 'antd/es/table';
import type { TaskExecution, ExecutionStep, ExecutionStatus, StepStatus } from '@/types/models';
import StepProgressBar, { type StepInfo } from '@/components/Pipeline/StepProgressBar';
import ExecutionMonitorPanel from './ExecutionMonitorPanel';
import DailyReportViewer from './analytics/DailyReportViewer';
import UnattendedLogViewer from './analytics/UnattendedLogViewer';
import DailySummaryCarousel from './analytics/DailySummaryCarousel';
import { wsClient } from '@/websocket/client';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;
const { TextArea } = Input;
const { Text } = Typography;

const EXECUTION_STATUS_COLOR_MAP: Record<ExecutionStatus, string> = {
  pending: 'blue',
  running: 'orange',
  paused: 'gold',
  success: 'green',
  failed: 'red',
  cancelled: 'default',
  force_terminated: 'red',
};

const EXECUTION_STATUS_LABEL_MAP: Record<ExecutionStatus, string> = {
  pending: 'executions.status_pending',
  running: 'executions.status_running',
  paused: 'executions.status_paused',
  success: 'executions.status_success',
  failed: 'executions.status_failed',
  cancelled: 'executions.status_cancelled',
  force_terminated: 'executions.status_force_terminated',
};

const STEP_STATUS_COLOR_MAP: Record<string, string> = {
  pending: 'blue',
  running: 'orange',
  success: 'green',
  failed: 'red',
  skipped: 'default',
};

const STEP_STATUS_LABEL_MAP: Record<string, string> = {
  pending: 'executions.step_status_pending',
  running: 'executions.step_status_running',
  success: 'executions.step_status_success',
  failed: 'executions.step_status_failed',
  skipped: 'executions.step_status_skipped',
};

function formatDuration(startedAt: string | null, completedAt: string | null): string {
  if (!completedAt) return '-';
  const ms = dayjs(completedAt).diff(dayjs(startedAt));
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}min`;
}

/** intervention operation Modal content */
function InterveneModal({
  open,
  action,
  executionId,
  onOk,
  onCancel,
}: {
  open: boolean;
  action: string;
  executionId: number;
  onOk: (reason: string) => void;
  onCancel: () => void;
}) {
  const t = useTranslation();
  const [reason, setReason] = useState('');
  const actionLabels: Record<string, string> = {
    pause: t('executions.action_pause'),
    resume: t('executions.action_resume'),
    skip_step: t('executions.action_skip_step'),
    cancel: t('executions.action_cancel'),
    fail_step: t('executions.action_fail_step'),
  };

  return (
    <Modal
      title={actionLabels[action] || action}
      open={open}
      onOk={() => onOk(reason)}
      onCancel={onCancel}
      okText={t('executions.modal_confirm')}
      cancelText={t('executions.modal_cancel')}
    >
      <Text>{t('executions.modal_confirm_action', { id: executionId, action: actionLabels[action] || action })}</Text>
      <TextArea
        placeholder={t('executions.placeholder_reason')}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="gaf-mt-md"
        rows={2}
      />
    </Modal>
  );
}

export function ExecutionsPage() {
  const { message: msg } = App.useApp();
  const { token } = antTheme.useToken();
  const t = useTranslation();
  const [executions, setExecutions] = useState<TaskExecution[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>();
  const [expandedRowKeys, setExpandedRowKeys] = useState<number[]>([]);
  const [stepsMap, setStepsMap] = useState<Record<number, { steps: ExecutionStep[]; total: number; completed: number }>>({});
  const [monitoringExecutionId, setMonitoringExecutionId] = useState<number | null>(null);
  const [monitoringAgentId, setMonitoringAgentId] = useState<string | undefined>();
  const [monitoringSteps, setMonitoringSteps] = useState<StepInfo[]>([]);
  const [activeTab, setActiveTab] = useState<string>('list');
  const [liveLogs, setLiveLogs] = useState<Record<string, string[]>>({});
  const [watchingId, setWatchingId] = useState<number | null>(null);
  const [interveneModal, setInterveneModal] = useState<{ open: boolean; action: string; executionId: number }>({
    open: false,
    action: '',
    executionId: 0,
  });
  const taskLogHandlerRef = useRef<((data: Record<string, unknown>) => void) | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  const loadExecutions = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: 20 };
      if (statusFilter) params.status = statusFilter;
      if (dateRange && dateRange[0] && dateRange[1]) {
        params.start_date = dateRange[0].format('YYYY-MM-DD');
        params.end_date = dateRange[1].format('YYYY-MM-DD');
      }
      const res = await fetchAllExecutions(params as Parameters<typeof fetchAllExecutions>[0]);
      setExecutions(res.results || []);
      setTotal(res.count);
    } catch {
      // load failed when keep existing data
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, dateRange]);

  useEffect(() => {
    loadExecutions();
  }, [loadExecutions]);

  const startWatching = (executionId: number) => {
    stopWatching();
    setLiveLogs((prev) => ({ ...prev, [executionId]: [] }));
    setWatchingId(executionId);

    const handler = (data: Record<string, unknown>) => {
      const typedData = data as { execution_id: string | number; message: string };
      if (String(typedData.execution_id) === String(executionId)) {
        setLiveLogs((prev) => ({
          ...prev,
          [executionId]: [...(prev[executionId] || []), typedData.message],
        }));
      }
    };

    taskLogHandlerRef.current = handler;
    wsClient.onMessage('task_log', handler);
  };

  const stopWatching = () => {
    if (taskLogHandlerRef.current) {
      wsClient.offMessage('task_log', taskLogHandlerRef.current);
      taskLogHandlerRef.current = null;
    }
    setWatchingId(null);
  };

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [liveLogs]);

  const handleExpand = async (expanded: boolean, record: TaskExecution) => {
    if (expanded) {
      setExpandedRowKeys([...expandedRowKeys, record.id]);
      if (!stepsMap[record.id]) {
        try {
          const detail = await fetchExecutionSteps(record.id);
          const stepList = detail.steps || [];
          setStepsMap((prev) => ({
            ...prev,
            [record.id]: { steps: stepList, total: detail.total_steps, completed: detail.completed_steps },
          }));
        } catch {
          // details load failed
        }
      }
    } else {
      setExpandedRowKeys(expandedRowKeys.filter((k) => k !== record.id));
    }
  };

  const convertStepsToStepInfo = (taskSteps: ExecutionStep[]): StepInfo[] => {
    return taskSteps.map((ts) => {
      const rawStatus: string = ts.status ?? '';
      const mappedStatus: StepStatus = rawStatus as StepStatus;
      // Task 4.31 (P1-20, 2026-07-28): 修复历史 REST 加载不展示 error_code Tag 问题。
      // Task 4.5 已通过 SerializerMethodField 从 ExecutionStep 关联读取 error_code,
      // REST /steps/ 端点会返回 error_code 字段; 但 OpenAPI schema 未同步更新,
      // 此处通过类型扩展访问 ts.error_code, 让历史执行也能展示多语言错误码 Tag,
      // 与 WS 实时事件 (handleStepUpdate 提取 error_code) 对称。
      const tsWithErrorCode = ts as ExecutionStep & { error_code?: string };
      return {
        index: ts.step_index,
        name: ts.step_name,
        status: mappedStatus,
        duration:
          ts.started_at && ts.completed_at
            ? new Date(ts.completed_at).getTime() - new Date(ts.started_at).getTime()
            : undefined,
        // Task 1.1 (N192 B3+B7): carry error_message so the retry-from-step
        // confirmation modal can show WHY the step failed. Without this,
        // the user sees only the step index + execution id — not actionable
        // for diagnosis. Folded into Task 1.1 per N193 task-ownership.
        error_message: ts.error_message,
        error_code: tsWithErrorCode.error_code || undefined,
      };
    });
  };

  const handleStartMonitoring = async (record: TaskExecution) => {
    setMonitoringExecutionId(record.id);
    // Use the Worker.agent_id string (e.g. "td010-repro-agent") for
    // screenshot stream routing. The backend Channels group is
    // `agent_{agent_id}` (string), NOT `agent_{DB pk}`. Passing the DB
    // id (record.agent, e.g. 4) would route to a non-existent group and
    // the stream would never start — leaving ExecutionMonitorPanel in
    // "等待截图数据" forever. See backend TaskExecutionSerializer
    // get_agent_identifier() for the source of this field.
    setMonitoringAgentId(record.agent_identifier ?? undefined);
    setActiveTab('monitor');

    if (!stepsMap[record.id]) {
      try {
        const detail = await fetchExecutionSteps(record.id);
        const stepList = detail.steps || [];
        setStepsMap((prev) => ({
          ...prev,
          [record.id]: { steps: stepList, total: detail.total_steps, completed: detail.completed_steps },
        }));
        setMonitoringSteps(convertStepsToStepInfo(stepList));
      } catch {
        // step load failed
      }
    } else {
      setMonitoringSteps(convertStepsToStepInfo(stepsMap[record.id].steps));
    }
  };

  const handleCloseMonitoring = () => {
    setMonitoringExecutionId(null);
    setMonitoringAgentId(undefined);
    setMonitoringSteps([]);
    setActiveTab('list');
  };

  const handleIntervene = async (reason: string) => {
    const { action, executionId } = interveneModal;
    setInterveneModal({ open: false, action: '', executionId: 0 });
    try {
      const res =
        action === 'pause'
          ? await pauseExecution(executionId, reason)
          : action === 'resume'
            ? await resumeExecution(executionId, reason)
            : action === 'skip_step'
              ? await skipExecutionStep(executionId, reason)
              : action === 'cancel'
                ? await cancelExecution(executionId, reason)
                : await failExecutionStep(executionId, reason);
      msg.success(res.message);
      loadExecutions();
    } catch {
      msg.error(t('executions.msg_action_failed'));
    }
  };

  const openInterveneModal = (action: string, executionId: number) => {
    setInterveneModal({ open: true, action, executionId });
  };

  const stepColumns: ColumnsType<ExecutionStep> = [
    { title: t('executions.col_step_index'), dataIndex: 'step_index', key: 'step_index', width: 60 },
    { title: t('executions.col_step_name'), dataIndex: 'name', key: 'name', width: 160, ellipsis: true },
    { title: t('executions.col_description'), dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: t('executions.col_status'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => (
        <Tag color={STEP_STATUS_COLOR_MAP[status] || 'default'}>
          {t(STEP_STATUS_LABEL_MAP[status] || 'executions.col_status')}
        </Tag>
      ),
    },
    {
      // Task 4.17 (P1-16, 2026-07-28): 失败步骤展示 error_message,
      // 让用户在执行列表 tab 就能看到失败原因, 不用切到"监控"tab.
      title: t('executions.col_error_message'),
      dataIndex: 'error_message',
      key: 'error_message',
      width: 200,
      ellipsis: true,
      render: (msg: string, record) => {
        if (record.status !== 'failed' || !msg) return '-';
        return (
          <Text type="danger" title={msg}>
            {msg}
          </Text>
        );
      },
    },
    {
      title: t('executions.col_started_at'),
      dataIndex: 'started_at',
      key: 'started_at',
      width: 180,
      render: (val: string | null) => (val ? dayjs(val).locale('zh-cn').format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: t('executions.col_duration'),
      key: 'duration',
      width: 100,
      render: (_, record) => formatDuration(record.started_at ?? null, record.completed_at ?? null),
    },
  ];

  // TD-407 (2026-08-27): executions list shows display names instead of raw FK
  // ids — the backend serializer now exposes task_name / agent_hostname.
  type ExecRow = TaskExecution & { task_name?: string; agent_hostname?: string };

  const columns: ColumnsType<ExecRow> = [
    {
      title: t('executions.col_id'),
      dataIndex: 'id',
      key: 'id',
      width: 120,
      ellipsis: true,
    },
    {
      title: t('executions.col_task'),
      dataIndex: 'task',
      key: 'task',
      width: 160,
      ellipsis: true,
      render: (value, record) => record.task_name || value,
    },
    {
      title: t('executions.col_agent'),
      dataIndex: 'agent',
      key: 'agent',
      width: 160,
      ellipsis: true,
      render: (value, record) => record.agent_hostname || value,
    },
    {
      title: t('executions.col_status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: ExecutionStatus) => (
        <Tag color={EXECUTION_STATUS_COLOR_MAP[status]}>{t(EXECUTION_STATUS_LABEL_MAP[status])}</Tag>
      ),
    },
    {
      title: t('executions.col_started_at'),
      dataIndex: 'started_at',
      key: 'started_at',
      width: 180,
      render: (val: string) => (val ? dayjs(val).locale('zh-cn').format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: t('executions.col_duration'),
      key: 'duration',
      width: 100,
      render: (_, record) => formatDuration(record.started_at ?? null, record.completed_at ?? null),
    },
    {
      title: t('executions.col_action'),
      key: 'action',
      width: 280,
      render: (_, record) => {
        const isRunning = record.status === 'running';
        const isPaused = record.status === 'paused';
        return (
          <div className="gaf-flex-center gaf-gap-xs">
            <Button
              key="detail"
              type="link"
              size="small"
              onClick={() => handleExpand(!expandedRowKeys.includes(record.id), record)}
            >
              {expandedRowKeys.includes(record.id) ? t('executions.btn_collapse') : t('executions.btn_detail')}
            </Button>
            {isRunning && (
              <>
                <Tooltip key="pause" title={t('executions.tooltip_pause')}>
                  <Button
                    type="link"
                    size="small"
                    icon={<PauseCircleOutlined />}
                    aria-label={t('executions.tooltip_pause')}
                    onClick={() => openInterveneModal('pause', record.id)}
                  />
                </Tooltip>
                <Tooltip key="skip" title={t('executions.tooltip_skip_step')}>
                  <Button
                    type="link"
                    size="small"
                    icon={<StepForwardOutlined />}
                    aria-label={t('executions.tooltip_skip_step')}
                    onClick={() => openInterveneModal('skip_step', record.id)}
                  />
                </Tooltip>
                <Tooltip key="cancel" title={t('executions.tooltip_cancel')}>
                  <Button
                    type="link"
                    size="small"
                    danger
                    icon={<StopOutlined />}
                    aria-label={t('executions.tooltip_cancel')}
                    onClick={() => openInterveneModal('cancel', record.id)}
                  />
                </Tooltip>
                <Tooltip key="fail" title={t('executions.tooltip_force_fail')}>
                  <Button
                    type="link"
                    size="small"
                    danger
                    icon={<CloseCircleOutlined />}
                    aria-label={t('executions.tooltip_force_fail')}
                    onClick={() => openInterveneModal('fail_step', record.id)}
                  />
                </Tooltip>
              </>
            )}
            {isPaused && (
              <Tooltip key="resume" title={t('executions.tooltip_resume')}>
                <Button
                  type="link"
                  size="small"
                  icon={<CaretRightOutlined />}
                  aria-label={t('executions.tooltip_resume')}
                  style={{ color: token.colorSuccess }}
                  onClick={() => openInterveneModal('resume', record.id)}
                />
              </Tooltip>
            )}
            <Tooltip key="monitor" title={t('executions.tooltip_monitor')}>
              <Button type="primary" size="small" icon={<EyeOutlined />} onClick={() => handleStartMonitoring(record)}>
                {t('executions.btn_monitor')}
              </Button>
            </Tooltip>
            <Tooltip key="log" title={t('executions.tooltip_log')}>
              <Button
                type="link"
                size="small"
                icon={<UnorderedListOutlined />}
                onClick={() => (watchingId === record.id ? stopWatching() : startWatching(record.id))}
              >
                {watchingId === record.id ? t('executions.btn_stop') : t('executions.btn_log')}
              </Button>
            </Tooltip>
          </div>
        );
      },
    },
  ];

  return (
    <PageWrapper
      title={t('executions.page_title')}
      extra={
        <Space>
          {monitoringExecutionId && (
            <Button size="small" onClick={handleCloseMonitoring}>
              {t('executions.btn_close_monitor')}
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={loadExecutions}>
            {t('executions.btn_refresh')}
          </Button>
        </Space>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key)}
        items={[
          {
            key: 'list',
            label: (
              <span>
                <span aria-hidden="true">
                  <UnorderedListOutlined />
                </span>{' '}
                {t('executions.tab_list')}
              </span>
            ),
            children: (
              <>
                <Space className="gaf-mb-lg" wrap>
                  <Select
                    placeholder={t('executions.placeholder_filter_status')}
                    allowClear
                    style={{ width: 150 }}
                    value={statusFilter}
                    onChange={(val) => {
                      setStatusFilter(val);
                      setPage(1);
                    }}
                    options={Object.entries(EXECUTION_STATUS_LABEL_MAP).map(([value, key]) => ({
                      value,
                      label: t(key),
                    }))}
                  />
                  <RangePicker
                    value={dateRange}
                    onChange={(dates) => {
                      setDateRange(dates);
                      setPage(1);
                    }}
                  />
                </Space>

                {loading ? (
                  <Skeleton active title={false} paragraph={{ rows: 10 }} />
                ) : (
                  <Table
                    columns={columns}
                    dataSource={executions || []}
                    rowKey="id"
                    expandable={{
                      expandedRowKeys,
                      onExpand: handleExpand,
                      expandedRowRender: (record) => {
                        const stepData = stepsMap[record.id];
                        const stepList = stepData?.steps || [];
                        const stepTotal = stepData?.total || stepList.length;
                        const stepCompleted =
                          stepData?.completed || stepList.filter((s) => s.status === 'success').length;
                        const failureReason = record.error_message || record.cancel_reason;
                        return (
                          <div>
                            {failureReason && (
                              <Alert
                                type={record.status === 'cancelled' ? 'warning' : 'error'}
                                showIcon
                                title={
                                  record.status === 'cancelled'
                                    ? t('executions.text_cancel_reason')
                                    : t('executions.text_failure_reason')
                                }
                                description={failureReason}
                                className="gaf-mb-md"
                              />
                            )}
                            <div className="gaf-flex gaf-gap-xl gaf-mb-md">
                              <div>
                                <Text type="secondary">{t('executions.text_step_progress')}</Text>
                                <Progress
                                  percent={stepTotal > 0 ? Math.round((stepCompleted / stepTotal) * 100) : 0}
                                  status={stepCompleted === stepTotal && stepTotal > 0 ? 'success' : 'active'}
                                  size="small"
                                  className="gaf-w-200"
                                />
                              </div>
                              <Text type="secondary">
                                {stepCompleted}/{stepTotal} {t('executions.text_completed')}
                              </Text>
                            </div>
                            {/* Task 4.55 (P1-35, 2026-07-28): 替换 antd Steps 为 StepProgressBar,与 monitor tab 一致展示 error_code/error_message */}
                            <StepProgressBar
                              steps={convertStepsToStepInfo(stepList)}
                              currentStepIndex={stepCompleted}
                              onStepClick={() => {}}
                            />
                            <Table
                              columns={stepColumns}
                              dataSource={stepList}
                              rowKey="id"
                              pagination={false}
                              size="small"
                              className="gaf-mt-md"
                            />
                          </div>
                        );
                      },
                    }}
                    pagination={{
                      total,
                      current: page,
                      pageSize: 20,
                      showTotal: (count) => t('executions.text_pagination_total', { count }),
                      onChange: (p) => setPage(p),
                    }}
                  />
                )}
              </>
            ),
          },
          ...(monitoringExecutionId
            ? [
                {
                  key: 'monitor',
                  label: (
                    <span>
                      <span aria-hidden="true">
                        <DashboardOutlined />
                      </span>{' '}
                      {t('executions.tab_monitor')}
                    </span>
                  ),
                  children: (
                    <ExecutionMonitorPanel
                      executionId={monitoringExecutionId}
                      agentId={monitoringAgentId}
                      steps={monitoringSteps}
                    />
                  ),
                },
              ]
            : []),
          {
            key: 'daily-report',
            label: <span>📋 {t('executions.tab_daily_report')}</span>,
            children: <DailyReportViewer />,
          },
          {
            key: 'unattended-logs',
            label: <span>📜 {t('executions.tab_unattended_logs')}</span>,
            children: <UnattendedLogViewer />,
          },
          {
            key: 'summary-carousel',
            label: <span>🎯 {t('executions.tab_summary_carousel')}</span>,
            children: <DailySummaryCarousel />,
          },
        ]}
      />

      {watchingId && liveLogs[watchingId] && (
        <div className="gaf-mt-lg">
          <h3>{t('executions.text_live_log_title', { id: watchingId })}</h3>
          <TextArea
            value={liveLogs[watchingId].join('\n')}
            readOnly
            autoSize={{ minRows: 8, maxRows: 20 }}
            className="gaf-text-xs gaf-font-mono"
            style={{ backgroundColor: token.colorBgLayout, color: token.colorText }}
          />
          <div ref={logEndRef} />
        </div>
      )}

      <InterveneModal
        open={interveneModal.open}
        action={interveneModal.action}
        executionId={interveneModal.executionId}
        onOk={handleIntervene}
        onCancel={() => setInterveneModal({ open: false, action: '', executionId: 0 })}
      />
    </PageWrapper>
  );
}

export default ExecutionsPage;
