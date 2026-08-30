/**
 * dashboard page — GAF V3
 * layout structure ( vertical directly streaming layout ):
 * - title area: workspace + system run row overview
 * - 1st row: today schedule timeline
 * - 2nd row: system stats card ( in online Worker/ run row task / today execute / success rate )
 * - 3rd row:Worker health panel
 * - 4th row: most recent execute record
 * - 5th row: shortcut operation
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { Card, Statistic, Table, Tag, Skeleton, Row, Col, Empty, Typography, theme as antTheme } from 'antd';
import {
  DesktopOutlined,
  ScheduleOutlined,
  CheckCircleOutlined,
  RiseOutlined,
  HolderOutlined,
} from '@ant-design/icons';
import { useDeviceStore } from '@/stores/useDeviceStore';
import { useTaskStore } from '@/stores/useTaskStore';
import { fetchExecutions, getDashboardDailyReport } from '@/api/tasks';
import { useTranslation, getLocale } from '@/i18n';
import type { DashboardStats, TaskExecution } from '@/types/models';
import type { ColumnsType } from 'antd/es/table';
import QuickActions from './QuickActions';
import AgentHealthPanel from './AgentHealthPanel';
import TodaySchedule from '@/components/Dashboard/TodaySchedule';
import ProgressRing from '@/components/Dashboard/ProgressRing';
import ExecutionQueuePreview from '@/components/Dashboard/ExecutionQueuePreview';
import AlertSummary from '@/components/Dashboard/AlertSummary';
import TrendChart from '@/components/Dashboard/TrendChart';
import UnattendedControl from '@/components/Dashboard/UnattendedControl';
import PageWrapper from '@/components/Common/PageWrapper';

type WidgetType =
  | 'task_overview'
  | 'device_status'
  | 'recent_executions'
  | 'quick_actions'
  | 'progress_ring'
  | 'execution_queue'
  | 'alert_summary'
  | 'trend_chart'
  | 'unattended_control';

interface WidgetConfig {
  id: WidgetType;
  title: string;
  span: number;
}

const WIDGET_LAYOUT_KEY = 'gaf_dashboard_widgets';

function loadWidgetLayout(): WidgetConfig[] {
  try {
    const stored = localStorage.getItem(WIDGET_LAYOUT_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {
    /* ignore */
  }
  // Default layout (titles filled at runtime via i18n)
  return [
    { id: 'task_overview', title: '', span: 24 },
    { id: 'progress_ring', title: '', span: 24 },
    { id: 'device_status', title: '', span: 24 },
    { id: 'execution_queue', title: '', span: 24 },
    { id: 'recent_executions', title: '', span: 24 },
    { id: 'trend_chart', title: '', span: 24 },
    { id: 'alert_summary', title: '', span: 24 },
    { id: 'unattended_control', title: '', span: 24 },
    { id: 'quick_actions', title: '', span: 24 },
  ];
}

function saveWidgetLayout(widgets: WidgetConfig[]): void {
  localStorage.setItem(WIDGET_LAYOUT_KEY, JSON.stringify(widgets));
}

interface RecentExecution {
  id: string;
  name: string;
  status: string;
  time: string;
}

export function DashboardPage() {
  const { token } = antTheme.useToken();
  const t = useTranslation();
  const [stats, setStats] = useState<DashboardStats>({
    online_agents: 0,
    running_tasks: 0,
    today_executions: 0,
    success_rate: 0,
  });
  const [statsLoading, setStatsLoading] = useState(true);
  const [recentExecutions, setRecentExecutions] = useState<RecentExecution[]>([]);
  const { fetchAgents } = useDeviceStore();
  const { fetchTasks } = useTaskStore();

  const [widgets, setWidgets] = useState<WidgetConfig[]>(loadWidgetLayout);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const dragSource = useRef<number | null>(null);
  const dragTarget = useRef<number | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        await Promise.all([fetchAgents(), fetchTasks()]);

        const [dailyData, runningData, recentData] = await Promise.all([
          getDashboardDailyReport().catch((err: unknown) => {
            console.error('Dashboard daily report load failed:', err);
            return null;
          }),
          fetchExecutions({ status: 'running' }).catch((err: unknown) => {
            console.error('Dashboard running executions load failed:', err);
            return null;
          }),
          fetchExecutions({ page_size: 5, ordering: '-created_at' }).catch((err: unknown) => {
            console.error('Dashboard recent executions load failed:', err);
            return null;
          }),
        ]);

        const currentAgents = useDeviceStore.getState().agents;
        const currentTasks = useTaskStore.getState().tasks;

        const onlineCount = currentAgents.filter((a) => a.status !== 'offline').length;
        const runningCount = runningData?.count ?? runningData?.results?.length ?? 0;

        let todayExecutions = 0;
        let successRate = 0;
        if (dailyData?.overview) {
          todayExecutions = dailyData.overview.total_executions || 0;
          successRate = dailyData.overview.success_rate || 0;
        }

        setStats({
          online_agents: onlineCount,
          running_tasks: runningCount,
          today_executions: todayExecutions,
          success_rate: successRate,
        });

        const localeMap: Record<string, string> = {
          'zh-CN': 'zh-CN',
          'en-US': 'en-US',
          'ja-JP': 'ja-JP',
          'ko-KR': 'ko-KR',
        };
        const dateLocale = localeMap[getLocale()] || 'en-US';
        const taskNameMap = new Map(currentTasks.map((t) => [t.id, t.name]));
        const recentExecs: TaskExecution[] = recentData?.results?.slice(0, 5) || [];
        const execs: RecentExecution[] = recentExecs.map((ex) => ({
          id: String(ex.id),
          name: taskNameMap.get(ex.task ?? 0) ?? `Task #${ex.task ?? '?'}`,
          status: ex.status ?? '',
          time: ex.created_at ? new Date(ex.created_at).toLocaleString(dateLocale) : '-',
        }));
        setRecentExecutions(execs);
      } catch (err: unknown) {
        // Cancel/abort errors are navigation/unmount noise, not real failures —
        // don't log them as errors.
        const e = err as { name?: string; code?: string } | null;
        if (e?.name && (e.name === 'AbortError' || e.name === 'CanceledError' || e.code === 'ERR_CANCELED')) {
          // silent
        } else {
          console.error('Dashboard stats load failed:', err);
        }
      } finally {
        setStatsLoading(false);
      }
    };
    loadData();
  }, [fetchAgents, fetchTasks]);

  const handleDragStart = useCallback((index: number) => {
    dragSource.current = index;
    setDraggingIndex(index);
    setDragOverIndex(null);
  }, []);
  const handleDragOver = useCallback((e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    dragTarget.current = index;
    setDragOverIndex(index);
  }, []);
  const handleDrop = useCallback(
    (index: number) => {
      if (dragSource.current === null || dragSource.current === index) return;
      const newWidgets = [...widgets];
      const [moved] = newWidgets.splice(dragSource.current, 1);
      newWidgets.splice(index, 0, moved);
      setWidgets(newWidgets);
      saveWidgetLayout(newWidgets);
      dragSource.current = null;
      dragTarget.current = null;
      setDraggingIndex(null);
      setDragOverIndex(null);
    },
    [widgets],
  );
  const handleDragEnd = useCallback(() => {
    dragSource.current = null;
    dragTarget.current = null;
    setDraggingIndex(null);
    setDragOverIndex(null);
  }, []);

  const executionColumns: ColumnsType<RecentExecution> = [
    {
      title: t('dashboard.col_task_name'),
      dataIndex: 'name',
      key: 'name',
      render: (v: string) => <strong>{v}</strong>,
    },
    {
      title: t('dashboard.col_status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          success: 'green',
          running: 'blue',
          pending: 'cyan',
          paused: 'orange',
          failed: 'red',
          cancelled: 'default',
          force_terminated: 'red',
          idle: 'default',
        };
        const labelKey: Record<string, string> = {
          success: 'dashboard.status_success',
          running: 'dashboard.status_running',
          pending: 'dashboard.status_pending',
          paused: 'dashboard.status_paused',
          failed: 'dashboard.status_failed',
          cancelled: 'dashboard.status_cancelled',
          force_terminated: 'dashboard.status_force_terminated',
          idle: 'dashboard.status_idle',
        };
        return <Tag color={colorMap[status] || 'default'}>{t(labelKey[status] || '') || status}</Tag>;
      },
    },
    { title: t('dashboard.col_time'), dataIndex: 'time', key: 'time' },
  ];

  const renderStatsCard = (widget: WidgetConfig) => {
    if (widget.id === 'task_overview') {
      return (
        <Card>
          <Row gutter={[24, 16]}>
            <Col xs={12} sm={6}>
              <Statistic
                title={t('dashboard.stat_online_agents')}
                value={stats.online_agents}
                prefix={
                  <span aria-hidden="true">
                    <DesktopOutlined />
                  </span>
                }
                styles={{ content: { color: token.colorSuccess } }}
              />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic
                title={t('dashboard.stat_running_tasks')}
                value={stats.running_tasks}
                prefix={
                  <span aria-hidden="true">
                    <ScheduleOutlined />
                  </span>
                }
                styles={{ content: { color: token.colorPrimary } }}
              />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic
                title={t('dashboard.stat_today_executions')}
                value={stats.today_executions}
                prefix={
                  <span aria-hidden="true">
                    <CheckCircleOutlined />
                  </span>
                }
              />
            </Col>
            <Col xs={12} sm={6}>
              <Statistic
                title={t('dashboard.stat_success_rate')}
                value={stats.success_rate}
                suffix="%"
                prefix={
                  <span aria-hidden="true">
                    <RiseOutlined />
                  </span>
                }
                styles={{ content: { color: stats.success_rate >= 80 ? token.colorSuccess : token.colorError } }}
              />
            </Col>
          </Row>
        </Card>
      );
    }

    if (widget.id === 'device_status') {
      return <AgentHealthPanel />;
    }
    return null;
  };

  const renderContentCard = (widget: WidgetConfig) => {
    if (widget.id === 'recent_executions') {
      return (
        <Card title={t('dashboard.widget_recent_executions')}>
          {recentExecutions.length === 0 ? (
            <Empty description={t('dashboard.empty_executions')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Table
              columns={executionColumns}
              dataSource={recentExecutions}
              rowKey="id"
              size="small"
              pagination={false}
            />
          )}
        </Card>
      );
    }
    if (widget.id === 'quick_actions') {
      return <QuickActions />;
    }
    if (widget.id === 'progress_ring') {
      return <ProgressRing />;
    }
    if (widget.id === 'execution_queue') {
      return <ExecutionQueuePreview />;
    }
    if (widget.id === 'alert_summary') {
      return <AlertSummary />;
    }
    if (widget.id === 'trend_chart') {
      return <TrendChart />;
    }
    if (widget.id === 'unattended_control') {
      return <UnattendedControl />;
    }
    return null;
  };

  const renderWidgetContent = (widget: WidgetConfig) => {
    if (widget.id === 'task_overview' || widget.id === 'device_status') return renderStatsCard(widget);
    return renderContentCard(widget);
  };

  return (
    <PageWrapper title={t('dashboard.page_title')}>
      {statsLoading ? (
        <>
          <Skeleton active paragraph={{ rows: 2 }} className="gaf-mb-xl" />
          <Skeleton active paragraph={{ rows: 6 }} className="gaf-mb-xl" />
          <Skeleton active paragraph={{ rows: 4 }} className="gaf-mb-xl" />
          <Skeleton active paragraph={{ rows: 3 }} className="gaf-mb-xl" />
          <Skeleton active paragraph={{ rows: 5 }} />
        </>
      ) : (
        <>
          <div className="gaf-mb-xl">
            <Typography.Text type="secondary" className="gaf-text-sm">
              {t('dashboard.page_subtitle')}
            </Typography.Text>
          </div>

          {/* Row 1: Today's schedule timeline - full width */}
          <div className="gaf-mb-xl">
            <TodaySchedule />
          </div>

          {/* Rows 2-5: draggable widget cards - each takes a full row */}
          <div className="gaf-flex-col gaf-gap-xl">
            {widgets.map((widget, index) => {
              const isDragging = draggingIndex === index;
              const isDragOver = dragOverIndex === index;
              return (
                <div
                  key={widget.id}
                  draggable
                  className="gaf-radius-lg gaf-position-relative"
                  onDragStart={() => handleDragStart(index)}
                  onDragOver={(e) => handleDragOver(e, index)}
                  onDrop={() => handleDrop(index)}
                  onDragEnd={handleDragEnd}
                  style={{
                    transition: 'opacity 0.2s ease, transform 0.2s ease',
                    opacity: isDragging ? 0.4 : 1,
                    transform: isDragging ? 'scale(0.98)' : 'scale(1)',
                    outline: isDragOver ? `2px dashed ${token.colorPrimary}` : 'none',
                    outlineOffset: isDragOver ? 4 : 0,
                    cursor: 'grab',
                  }}
                  onMouseEnter={(e) => {
                    const handle = e.currentTarget.querySelector('.drag-handle') as HTMLElement;
                    if (handle) handle.style.opacity = '1';
                  }}
                  onMouseLeave={(e) => {
                    const handle = e.currentTarget.querySelector('.drag-handle') as HTMLElement;
                    if (handle) handle.style.opacity = '0';
                  }}
                >
                  {renderWidgetContent(widget)}
                  <div
                    className="drag-handle gaf-text-xs gaf-position-absolute gaf-flex-center gaf-justify-center"
                    style={{
                      top: 8,
                      right: 8,
                      width: 28,
                      height: 28,
                      borderRadius: 4,
                      zIndex: 10,
                      background: token.colorBgContainer,
                      boxShadow: '0 1px 2px rgba(0,0,0,0.06)',
                      cursor: 'grab',
                      color: token.colorTextTertiary,
                      opacity: 0,
                      transition: 'opacity 0.15s ease',
                    }}
                    title={t('dashboard.drag_hint')}
                    role="button"
                    aria-label={t('dashboard.drag_aria_label')}
                    tabIndex={0}
                  >
                    <HolderOutlined />
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </PageWrapper>
  );
}

export default DashboardPage;
