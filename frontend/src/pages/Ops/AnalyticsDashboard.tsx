/**
 * performance analysis dashboard page
 * use antd Statistic/Table/Progress show execute stats, step elapsed when ranking, trend, week report,Agent to compare
 */
import { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Table, Progress, Spin, Tag, theme as antTheme } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  RiseOutlined,
  FallOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  fetchStepHeatmap,
  fetchAnalyticsTrend,
  fetchWeeklyReport,
  fetchAgentPerformance,
  type TrendItem,
} from '@/api/ops';
import { useAuthStore } from '@/stores/useAuthStore';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

/** step elapsed when record item */
interface StepHeatItem {
  step_type: string;
  avg_duration_ms: number;
  execution_count: number;
}

/** week report data */
interface WeeklyReport {
  total_executions: number;
  success_count: number;
  failed_count: number;
  most_executed_task: string;
  avg_step_duration_ms: number;
  success_rate: number;
  recovery_triggered_count: number;
  avg_recovery_attempts: number;
  recovery_success_rate: number | null;
}

/** Agent performance record item */
interface AgentPerfItem {
  agent_name: string;
  execution_count: number;
  success_rate: number;
  avg_duration_ms: number;
}

/** performance analysis dashboard page component */
export function AnalyticsDashboardPage() {
  const { isAuthenticated } = useAuthStore();
  const { token } = antTheme.useToken();
  const t = useTranslation();
  const [stats, setStats] = useState({ total: 0, success_rate: 0, avg_duration: 0, running: 0, failed: 0 });
  const [stepData, setStepData] = useState<StepHeatItem[]>([]);
  const [trendData, setTrendData] = useState<TrendItem[]>([]);
  const [weeklyReport, setWeeklyReport] = useState<WeeklyReport | null>(null);
  const [agentData, setAgentData] = useState<AgentPerfItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) return;
    loadAll();
  }, [isAuthenticated]);

  /** load has analysis data */
  const loadAll = async () => {
    setLoading(true);
    try {
      const [stepRes, trendRes, weeklyRes, agentRes] = await Promise.allSettled([
        fetchStepHeatmap(),
        fetchAnalyticsTrend(),
        fetchWeeklyReport(),
        fetchAgentPerformance(),
      ]);

      if (stepRes.status === 'fulfilled') setStepData(Array.isArray(stepRes.value) ? stepRes.value : []);
      if (trendRes.status === 'fulfilled') setTrendData(Array.isArray(trendRes.value) ? trendRes.value : []);
      if (weeklyRes.status === 'fulfilled' && typeof weeklyRes.value === 'object' && weeklyRes.value !== null)
        setWeeklyReport(weeklyRes.value as WeeklyReport);
      if (agentRes.status === 'fulfilled') setAgentData(Array.isArray(agentRes.value) ? agentRes.value : []);

      // calculate summary stats — backend trend entries use execution_count +
      // success_rate; success/failed are derived (success_rate is percent).
      const trends: TrendItem[] =
        trendRes.status === 'fulfilled' && Array.isArray(trendRes.value) ? trendRes.value : [];
      const total = trends.reduce(
        (s: number, t: TrendItem) => s + (Number.isFinite(t.execution_count) ? t.execution_count : 0),
        0,
      );
      const totalSuccess = trends.reduce(
        (s: number, t: TrendItem) =>
          s +
          Math.round(
            ((Number.isFinite(t.execution_count) ? t.execution_count : 0) *
              (Number.isFinite(t.success_rate) ? t.success_rate : 0)) /
              100,
          ),
        0,
      );
      const totalFailed = total - totalSuccess;
      const avgDuration =
        stepData.length > 0 ? stepData.reduce((s, d) => s + d.avg_duration_ms, 0) / stepData.length : 0;

      setStats({
        total,
        success_rate: total > 0 ? Math.round((totalSuccess / total) * 1000) / 10 : 0,
        avg_duration: Math.round(avgDuration),
        running: trends.filter((t) => (Number.isFinite(t.execution_count) ? t.execution_count : 0) > 0).length,
        failed: totalFailed,
      });
    } catch {
      // pass
    } finally {
      setLoading(false);
    }
  };

  /** step elapsed when ranking column config */
  const stepColumns = [
    { title: t('analytics.col_step_type'), dataIndex: 'step_type', key: 'step_type' },
    {
      title: t('analytics.col_avg_duration'),
      dataIndex: 'avg_duration_ms',
      key: 'avg_duration_ms',
      sorter: (a: StepHeatItem, b: StepHeatItem) => a.avg_duration_ms - b.avg_duration_ms,
      render: (val: number) => <span className="gaf-font-medium">{val.toFixed(1)}</span>,
    },
    {
      title: t('analytics.col_relative'),
      key: 'relative',
      render: (_: unknown, record: StepHeatItem) => {
        const max = Math.max(...stepData.map((d) => d.avg_duration_ms), 1);
        return (
          <Progress
            percent={Math.round((record.avg_duration_ms / max) * 100)}
            size="small"
            showInfo={false}
            strokeColor={token.colorPrimary}
          />
        );
      },
    },
    { title: t('analytics.col_exec_count'), dataIndex: 'execution_count', key: 'execution_count' },
  ];

  /** trend table column config */
  const trendColumns = [
    // Backend trend entries expose execution_count + success_rate (percent).
    // Derive success/failed counts for display.
    { title: t('analytics.col_date'), dataIndex: 'date', key: 'date', render: (v: string) => dayjs(v).format('MM-DD') },
    { title: t('analytics.col_total'), dataIndex: 'execution_count', key: 'execution_count' },
    {
      title: t('analytics.col_success'),
      key: 'success',
      render: (_: unknown, r: TrendItem) => (
        <span style={{ color: token.colorSuccess }}>
          {Math.round(
            ((Number.isFinite(r.execution_count) ? r.execution_count : 0) *
              (Number.isFinite(r.success_rate) ? r.success_rate : 0)) /
              100,
          )}
        </span>
      ),
    },
    {
      title: t('analytics.col_failed'),
      key: 'failed',
      render: (_: unknown, r: TrendItem) => {
        const count = Number.isFinite(r.execution_count) ? r.execution_count : 0;
        const success = Math.round((count * (Number.isFinite(r.success_rate) ? r.success_rate : 0)) / 100);
        return <span style={{ color: token.colorError }}>{count - success}</span>;
      },
    },
    {
      title: t('analytics.col_success_rate'),
      dataIndex: 'success_rate',
      key: 'success_rate',
      render: (v: number) => <Tag color={v >= 95 ? 'green' : v >= 80 ? 'orange' : 'red'}>{v}%</Tag>,
    },
  ];

  /** Agent performance column config */
  const agentColumns = [
    { title: t('analytics.col_agent'), dataIndex: 'agent_name', key: 'agent_name' },
    { title: t('analytics.col_exec_count'), dataIndex: 'execution_count', key: 'execution_count' },
    {
      title: t('analytics.col_success_rate'),
      dataIndex: 'success_rate',
      key: 'success_rate',
      render: (v: number) => (
        <span style={{ color: v >= 95 ? token.colorSuccess : token.colorError }}>
          {v}% {v >= 95 ? <RiseOutlined /> : <FallOutlined />}
        </span>
      ),
    },
    {
      title: t('analytics.col_avg_duration'),
      dataIndex: 'avg_duration_ms',
      key: 'avg_duration_ms',
      render: (v: number) => `${v.toFixed(1)}`,
    },
  ];

  return (
    <PageWrapper title={t('analytics.page_title')}>
      <Spin spinning={loading}>
        {/* 统计卡片 */}
        <Row gutter={[16, 16]} className="gaf-mb-xl">
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title={t('analytics.stat_total')}
                value={stats.total}
                prefix={<SyncOutlined />}
                styles={{ content: { color: token.colorPrimary } }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title={t('analytics.stat_success_rate')}
                value={stats.success_rate}
                suffix="%"
                prefix={stats.success_rate >= 95 ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                styles={{ content: { color: stats.success_rate >= 95 ? token.colorSuccess : token.colorError } }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title={t('analytics.stat_avg_duration')}
                value={stats.avg_duration}
                suffix="ms"
                prefix={<ClockCircleOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title={t('analytics.stat_running_failed')}
                value={stats.running}
                suffix={`/ ${stats.failed}`}
                styles={{ content: { color: stats.failed > 0 ? token.colorWarning : token.colorSuccess } }}
              />
            </Card>
          </Col>
        </Row>

        {/* 步骤耗时排行榜 */}
        <Card title={t('analytics.card_step_rank')} className="gaf-mb-xl">
          <Table
            columns={stepColumns}
            dataSource={stepData || []}
            rowKey="step_type"
            size="small"
            pagination={false}
            locale={{ emptyText: t('analytics.empty_step') }}
          />
        </Card>

        {/* 执行趋势表 */}
        <Card title={t('analytics.card_trend')} className="gaf-mb-xl">
          <Table
            columns={trendColumns}
            dataSource={trendData || []}
            rowKey="date"
            size="small"
            pagination={{ pageSize: 10, showTotal: (total) => t('analytics.total_days', { count: total }) }}
            locale={{ emptyText: t('analytics.empty_trend') }}
          />
        </Card>

        {/* 周报 + Agent 对比 */}
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card title={t('analytics.card_weekly')}>
              {weeklyReport ? (
                <div>
                  <Row gutter={16}>
                    <Col span={8}>
                      <Statistic title={t('analytics.weekly_total')} value={weeklyReport.total_executions} />
                    </Col>
                    <Col span={8}>
                      <Statistic
                        title={t('analytics.weekly_success')}
                        value={weeklyReport.success_count}
                        styles={{ content: { color: token.colorSuccess } }}
                      />
                    </Col>
                    <Col span={8}>
                      <Statistic
                        title={t('analytics.weekly_failed')}
                        value={weeklyReport.failed_count}
                        styles={{
                          content: {
                            color: weeklyReport.failed_count > 0 ? token.colorError : token.colorTextTertiary,
                          },
                        }}
                      />
                    </Col>
                  </Row>
                  <div className="gaf-mt-lg">
                    <div className="gaf-mb-sm">
                      <strong>{t('analytics.weekly_most_task')}</strong>
                      {weeklyReport.most_executed_task || '-'}
                    </div>
                    <div className="gaf-mb-sm">
                      <strong>{t('analytics.weekly_success_rate')}</strong>
                      <Tag color={weeklyReport.success_rate >= 95 ? 'green' : 'orange'}>
                        {weeklyReport.success_rate}%
                      </Tag>
                    </div>
                    <div>
                      <strong>{t('analytics.weekly_avg_step')}</strong>
                      {weeklyReport.avg_step_duration_ms?.toFixed(1) || '-'} ms
                    </div>
                    <div className="gaf-mb-sm">
                      <strong>{t('analytics.weekly_recovery_triggered')}</strong>
                      {weeklyReport.recovery_triggered_count ?? '-'}
                    </div>
                    <div>
                      <strong>{t('analytics.weekly_recovery_success_rate')}</strong>
                      {weeklyReport.recovery_success_rate != null ? `${weeklyReport.recovery_success_rate}%` : '-'}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="gaf-p-xl gaf-text-center" style={{ color: token.colorTextTertiary }}>
                  {t('analytics.empty_weekly')}
                </div>
              )}
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title={t('analytics.card_agent')}>
              <Table
                columns={agentColumns}
                dataSource={agentData || []}
                rowKey="agent_name"
                size="small"
                pagination={false}
                locale={{ emptyText: t('analytics.empty_agent') }}
              />
            </Card>
          </Col>
        </Row>
      </Spin>
    </PageWrapper>
  );
}

export default AnalyticsDashboardPage;
