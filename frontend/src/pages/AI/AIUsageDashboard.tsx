/**
 * AI Usage Dashboard component
 * Displays AI request statistics, model usage distribution and daily request trends
 */
import { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Spin, Empty, theme } from 'antd';
import { RobotOutlined, CheckCircleOutlined, ThunderboltOutlined, DollarOutlined, ToolOutlined } from '@ant-design/icons';
import {
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { fetchAiUsageStats, fetchAgentEvaluation } from '@/api/ai';
import type { AgentEvaluation } from '@/api/ai';
import { useTranslation } from '@/i18n';
import { PageWrapper } from '@/components/Common/PageWrapper';

/** Usage stats data type */
interface UsageStats {
  total_requests: number;
  success_rate: number;
  total_tokens: number;
  estimated_cost: number;
  model_distribution: ModelDistributionItem[];
  daily_trend: DailyTrendItem[];
}

interface ModelDistributionItem {
  name: string;
  value: number;
}

interface DailyTrendItem {
  date: string;
  requests: number;
  tokens: number;
}

/** Pie chart color config */
const PIE_COLORS = ['#1890ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#13c2c2'];

export function AIUsageDashboard() {
  const t = useTranslation();
  const { token } = theme.useToken();
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [agentEval, setAgentEval] = useState<AgentEvaluation | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadStats();
    loadAgentEvaluation();
  }, []);

  /** Load agent evaluation metrics (Phase 3) */
  const loadAgentEvaluation = async () => {
    try {
      const data = await fetchAgentEvaluation({ days: 30 });
      setAgentEval(data);
    } catch (err) {
      console.error('Agent evaluation load failed:', err);
    }
  };

  /** Load usage statistics data */
  const loadStats = async () => {
    setLoading(true);
    try {
      const data = await fetchAiUsageStats({ days: 30 });
      setStats({
        total_requests: data.total_requests || 0,
        success_rate: data.success_rate || 0,
        total_tokens: data.total_tokens || 0,
        estimated_cost: data.estimated_cost || 0,
        model_distribution: Array.isArray(data.model_distribution) ? data.model_distribution : [],
        daily_trend: Array.isArray(data.daily_trend) ? data.daily_trend : [],
      });
    } catch (err) {
      console.error('AI usage stats load failed:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageWrapper>
      <Spin spinning={loading}>
        <Row gutter={[16, 16]} className="gaf-mb-xl">
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title={t('ailab.label_total_requests')}
                value={stats?.total_requests ?? 0}
                prefix={<RobotOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title={t('ailab.label_success_rate')}
                value={stats?.success_rate ?? 0}
                precision={1}
                suffix="%"
                prefix={<CheckCircleOutlined />}
                styles={{ content: { color: token.colorSuccess } }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title={t('ailab.label_total_tokens')}
                value={stats?.total_tokens ?? 0}
                prefix={<ThunderboltOutlined />}
                formatter={(value) => Number(value).toLocaleString()}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title={t('ailab.label_estimated_cost')}
                value={`$${(stats?.estimated_cost ?? 0).toFixed(2)}`}
                prefix={<DollarOutlined />}
              />
            </Card>
          </Col>
        </Row>

        {/* Agent evaluation metrics (Phase 3) */}
        <Card
          title={
            <span>
              <RobotOutlined /> {t('ailab.card_agent_result')}
            </span>
          }
          size="small"
          className="gaf-mb-lg"
        >
          {!agentEval || agentEval.total_sessions === 0 ? (
            <Empty description={t('ailab.empty_no_data')} />
          ) : (
            <Row gutter={[16, 16]}>
              <Col xs={12} sm={6}>
                <Statistic
                  title={t('ailab.label_agent_status')}
                  value={agentEval.total_sessions}
                  suffix={t('ailab.label_sessions_unit')}
                  prefix={<RobotOutlined />}
                />
              </Col>
              <Col xs={12} sm={6}>
                <Statistic
                  title={t('ailab.label_completion_rate')}
                  value={(agentEval.completion_rate * 100).toFixed(1)}
                  precision={1}
                  suffix="%"
                  prefix={<CheckCircleOutlined />}
                  styles={{ content: { color: token.colorSuccess } }}
                />
              </Col>
              <Col xs={12} sm={6}>
                <Statistic
                  title={t('ailab.label_avg_latency')}
                  value={agentEval.avg_latency_seconds.toFixed(1)}
                  suffix="s"
                  prefix={<ThunderboltOutlined />}
                />
              </Col>
              <Col xs={12} sm={6}>
                <Statistic
                  title={t('ailab.label_avg_tool_calls')}
                  value={agentEval.avg_tool_calls_per_session.toFixed(1)}
                  prefix={<ToolOutlined />}
                />
              </Col>
            </Row>
          )}
        </Card>

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={10}>
            <Card title={t('ailab.card_model_distribution')} loading={loading}>
              {!stats?.model_distribution?.length ? (
                <Empty description={t('ailab.empty_no_data')} />
              ) : (
                <ResponsiveContainer width="100%" height={320}>
                  <PieChart>
                    <Pie
                      data={stats.model_distribution}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={4}
                      dataKey="value"
                      label={({ name, percent }: { name: string; percent: number }) =>
                        `${name} ${(percent * 100).toFixed(0)}%`
                      }
                    >
                      {stats.model_distribution.map((_entry: unknown, index: number) => (
                        <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value: unknown) => Number(value).toLocaleString()} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </Card>
          </Col>

          <Col xs={24} lg={14}>
            <Card title={t('ailab.card_daily_trend')} loading={loading}>
              {!stats?.daily_trend?.length ? (
                <Empty description={t('ailab.empty_no_data')} />
              ) : (
                <ResponsiveContainer width="100%" height={320}>
                  <AreaChart data={stats.daily_trend} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tickFormatter={(val: string) => val.slice(5)} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="requests"
                      name={t('ailab.legend_requests')}
                      stackId="1"
                      stroke={token.colorPrimary}
                      fill={token.colorPrimary}
                      fillOpacity={0.3}
                    />
                    <Area
                      type="monotone"
                      dataKey="tokens"
                      name={t('ailab.legend_tokens')}
                      stackId="2"
                      stroke={token.colorSuccess}
                      fill={token.colorSuccess}
                      fillOpacity={0.3}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </Card>
          </Col>
        </Row>
      </Spin>
    </PageWrapper>
  );
}

export default AIUsageDashboard;
