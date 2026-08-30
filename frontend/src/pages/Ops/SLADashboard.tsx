/**
 * SLA performance monitor dashboard
 * show screenshot latency,OCR latency etc. key key performance metric,10 seconds auto refresh
 */
import { useEffect, useState, useMemo } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Badge, theme } from 'antd';
import { ClockCircleOutlined, ThunderboltOutlined, DashboardOutlined } from '@ant-design/icons';
import { fetchSlaMetrics } from '@/api/ops';
import type { SlaMetric } from '@/api/ops';
import { fetchAgents } from '@/api/agents';
import { useTranslation, getLocale } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

/** metric threshold value config (i18n key map) */
const METRIC_THRESHOLD_KEYS: Record<string, { threshold: number; unit: string; labelKey: string }> = {
  screenshot_latency: { threshold: 500, unit: 'ms', labelKey: 'sla.metric_screenshot_latency' },
  ocr_latency: { threshold: 1000, unit: 'ms', labelKey: 'sla.metric_ocr_latency' },
  click_latency: { threshold: 300, unit: 'ms', labelKey: 'sla.metric_click_latency' },
  template_match_latency: { threshold: 800, unit: 'ms', labelKey: 'sla.metric_template_match_latency' },
};

/** SLA monitor dashboard page component */
export function SLADashboard() {
  const t = useTranslation();
  const { token } = theme.useToken();
  const [metrics, setMetrics] = useState<SlaMetric[]>([]);
  const [loading, setLoading] = useState(false);
  const [onlineAgents, setOnlineAgents] = useState(0);

  const metricLabels = useMemo(() => {
    const map: Record<string, string> = {};
    Object.entries(METRIC_THRESHOLD_KEYS).forEach(([k, v]) => {
      map[k] = t(v.labelKey);
    });
    return map;
  }, [t]);

  /** load SLA metric */
  const loadMetrics = async () => {
    try {
      setLoading(true);
      const data = await fetchSlaMetrics();
      setMetrics(Array.isArray(data) ? data : (data as { results?: SlaMetric[] }).results || []);
    } catch (err) {
      console.error('SLA data load failed:', err);
    } finally {
      setLoading(false);
    }
  };

  /** load in online Worker count */
  const loadOnlineAgents = async () => {
    try {
      const data = await fetchAgents();
      const agents = Array.isArray(data) ? data : data.results || [];
      setOnlineAgents(agents.filter((a: { status: string }) => a.status !== 'offline').length);
    } catch (err) {
      console.error('SLA data load failed:', err);
    }
  };

  // M10: mount-only initial load + 30s polling interval — intentionally [] deps.
  // loadMetrics/loadOnlineAgents call setState synchronously; acceptable for polling.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    loadMetrics();
    loadOnlineAgents();
    const interval = setInterval(() => {
      loadMetrics();
      loadOnlineAgents();
    }, 30000);
    return () => clearInterval(interval);
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  /** calculate most new metric value */
  const getLatest = (metricName: string): SlaMetric | undefined => {
    const filtered = metrics.filter((m) => m.metric_name === metricName);
    if (filtered.length === 0) return undefined;
    return filtered.reduce((latest, curr) => (new Date(curr.timestamp) > new Date(latest.timestamp) ? curr : latest));
  };

  /** computes percentile value (null when no data — must not show fake 0.0ms) */
  const getPercentile = (metricName: string, percentile: number): number | null => {
    const values = metrics
      .filter((m) => m.metric_name === metricName)
      .map((m) => m.value)
      .sort((a, b) => a - b);
    if (values.length === 0) return null;
    const idx = Math.ceil((percentile / 100) * values.length) - 1;
    return values[Math.min(idx, values.length - 1)];
  };

  const screenshotLatest = getLatest('screenshot_latency');
  const screenshotP99 = getPercentile('screenshot_latency', 99);
  const screenshotP50 = getPercentile('screenshot_latency', 50);
  const ocrP50 = getPercentile('ocr_latency', 50);

  /** get most recent 20 record metric record. Memoized to avoid re-sorting
   *  on every render (e.g. when onlineAgents state changes). */
  const recentMetrics = useMemo(
    () => [...metrics].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).slice(0, 20),
    [metrics],
  );

  /** judge is no over threshold value */
  const isExceeded = (record: SlaMetric): boolean => {
    const cfg = METRIC_THRESHOLD_KEYS[record.metric_name];
    if (!cfg) return false;
    return record.value > cfg.threshold;
  };

  /** SLA detail table column config */
  const columns = [
    {
      title: t('sla.col_time'),
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 160,
      render: (v: string) => new Date(v).toLocaleString(getLocale()),
    },
    {
      title: t('sla.col_agent'),
      dataIndex: 'agent_name',
      key: 'agent_name',
      width: 120,
      render: (v: string | null | undefined) => v || '-',
    },
    {
      title: t('sla.col_metric'),
      dataIndex: 'metric_name',
      key: 'metric_name',
      width: 140,
      render: (v: string) => metricLabels[v] || v,
    },
    {
      title: t('sla.col_value'),
      dataIndex: 'value',
      key: 'value',
      width: 100,
      render: (v: number, record: SlaMetric) => (
        <span className="gaf-font-medium" style={{ color: isExceeded(record) ? token.colorError : token.colorSuccess }}>
          {v.toFixed(1)} {METRIC_THRESHOLD_KEYS[record.metric_name]?.unit || ''}
        </span>
      ),
    },
    {
      title: t('sla.col_threshold'),
      key: 'threshold',
      width: 100,
      render: (_: unknown, record: SlaMetric) => {
        const cfg = METRIC_THRESHOLD_KEYS[record.metric_name];
        return cfg ? `${cfg.threshold}${cfg.unit}` : '-';
      },
    },
    {
      title: t('sla.col_status'),
      key: 'status',
      width: 80,
      render: (_: unknown, record: SlaMetric) =>
        isExceeded(record) ? (
          <Tag color="red">{t('sla.status_exceeded')}</Tag>
        ) : (
          <Tag color="green">{t('sla.status_normal')}</Tag>
        ),
    },
  ];

  return (
    <PageWrapper title={t('sla.page_title')}>
      {/* 核心指标卡片 */}
      <Row gutter={[16, 16]} className="gaf-mb-xl">
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title={t('sla.stat_screenshot_p50')}
              value={screenshotP50 ?? '-'}
              suffix="ms"
              prefix={<ClockCircleOutlined />}
              styles={{ content: { color: screenshotP50 != null && screenshotP50 > 500 ? token.colorError : token.colorSuccess } }}
              precision={screenshotP50 != null ? 1 : undefined}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title={t('sla.stat_screenshot_p99')}
              value={screenshotP99 ?? '-'}
              suffix="ms"
              prefix={<ClockCircleOutlined />}
              styles={{ content: { color: screenshotP99 != null && screenshotP99 > 500 ? token.colorError : token.colorSuccess } }}
              precision={screenshotP99 != null ? 1 : undefined}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title={t('sla.stat_ocr_p50')}
              value={ocrP50 ?? '-'}
              suffix="ms"
              prefix={<ThunderboltOutlined />}
              styles={{ content: { color: ocrP50 != null && ocrP50 > 1000 ? token.colorError : token.colorSuccess } }}
              precision={ocrP50 != null ? 1 : undefined}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title={t('sla.stat_online_agents')}
              value={onlineAgents}
              prefix={onlineAgents > 0 ? <Badge status="success" /> : <Badge status="default" />}
              suffix={<DashboardOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* 最新指标明细 */}
      <Row gutter={[16, 16]} className="gaf-mb-xl">
        <Col span={24}>
          <Card
            title={t('sla.card_latest_metrics', {
              time: screenshotLatest
                ? new Date(screenshotLatest.timestamp).toLocaleString(getLocale())
                : t('sla.latest_metrics_empty'),
            })}
          >
            <Row gutter={16}>
              {['screenshot_latency', 'ocr_latency', 'click_latency', 'template_match_latency'].map((name) => {
                const latest = getLatest(name);
                const cfg = METRIC_THRESHOLD_KEYS[name];
                const exceeded = latest ? latest.value > cfg.threshold : false;
                return (
                  <Col key={name} xs={12} sm={6}>
                    <Statistic
                      title={metricLabels[name]}
                      value={latest?.value ?? '-'}
                      suffix={latest ? cfg.unit : ''}
                      precision={latest ? 1 : undefined}
                      styles={{
                        content: {
                          color: !latest ? token.colorTextTertiary : exceeded ? token.colorError : token.colorSuccess,
                          fontSize: 20,
                        },
                      }}
                    />
                  </Col>
                );
              })}
            </Row>
          </Card>
        </Col>
      </Row>

      {/* SLA 指标明细表 */}
      <Card title={t('sla.card_sla_detail')} loading={loading}>
        <Table
          columns={columns}
          dataSource={recentMetrics || []}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 15, showTotal: (total) => t('sla.total_count', { count: total }) }}
          locale={{ emptyText: t('sla.empty_sla') }}
        />
      </Card>
    </PageWrapper>
  );
}

export default SLADashboard;
