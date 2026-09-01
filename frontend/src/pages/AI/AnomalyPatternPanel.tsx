/**
 * Anomaly Pattern Discovery Panel
 * Detects recurring failure patterns from execution logs with LLM analysis
 */
import { useState } from 'react';
import {
  Card,
  Button,
  Select,
  Typography,
  Spin,
  Tag,
  Alert,
  Timeline,
  Empty,
  Space,
  App,
  Statistic,
  Row,
  Col,
  Progress,
  theme as antTheme,
} from 'antd';
import {
  SearchOutlined,
  WarningOutlined,
  BugOutlined,
  ThunderboltOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';

import { detectAnomalies } from '@/api/ai';
import { useTranslation } from '@/i18n';
import type { GlobalToken } from 'antd/es/theme/interface';

const { Text, Paragraph } = Typography;

/** Anomaly pattern data structure */
interface AnomalyPattern {
  pattern_text: string;
  occurrence_count: number;
  severity: 'critical' | 'high' | 'medium' | 'low';
  category: string;
  sample_messages: string[];
  first_seen: string;
}

/** Anomaly detection result interface */
interface AnomalyResult {
  patterns: AnomalyPattern[];
  summary: string;
  llm_analysis: string | null;
  stats: {
    failed_count: number;
    total_count: number;
    failure_rate: number;
    unique_errors: number;
  };
  total_analyzed: number;
}

/** Severity color mapping (uses design tokens for theme responsiveness) */
function getSeverityConfig(
  token: GlobalToken,
): Record<string, { color: string; labelKey: string; icon: React.ReactNode }> {
  return {
    critical: {
      color: token.colorErrorActive,
      labelKey: 'ailab.severity_critical',
      icon: <ExclamationCircleOutlined />,
    },
    high: { color: token.colorError, labelKey: 'ailab.severity_high', icon: <WarningOutlined /> },
    medium: { color: token.colorWarning, labelKey: 'ailab.severity_medium', icon: <BugOutlined /> },
    low: { color: token.colorSuccess, labelKey: 'ailab.severity_low', icon: <ThunderboltOutlined /> },
  };
}

/** Category display mapping */
const CATEGORY_LABELS: Record<string, string> = {
  timeout: 'ailab.category_timeout',
  recognition: 'ailab.category_recognition_failed',
  device: 'ailab.category_device',
  permission: 'ailab.category_permission',
  resource: 'ailab.category_resource',
  unknown: 'ailab.category_unknown',
};

/**
 * Anomaly Pattern Discovery Tab (merged into LogAnalysisPanel as the
 * "anomaly" tab — detects recurring failure patterns from execution logs).
 */
export function AnomalyPatternTab() {
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const severityConfig = getSeverityConfig(token);
  const { message: msgApi } = App.useApp();
  const [daysRange, setDaysRange] = useState(7);
  const [minOccurrences, setMinOccurrences] = useState(2);
  const [detecting, setDetecting] = useState(false);
  const [result, setResult] = useState<AnomalyResult | null>(null);

  /** Run anomaly detection analysis */
  const handleDetect = async () => {
    setDetecting(true);
    setResult(null);
    try {
      const data = await detectAnomalies({
        days: daysRange,
        min_occurrences: minOccurrences,
      });
      setResult(data);
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : t('ailab.msg_detect_request_failed');
      msgApi.error(t('ailab.msg_anomaly_detect_failed', { message: errMsg }));
    } finally {
      setDetecting(false);
    }
  };

  /** Get timeline item color based on severity */
  const getSeverityColor = (severity: string) => {
    return severityConfig[severity]?.color || 'blue';
  };

  return (
    <div className="gaf-p-xl gaf-h-full gaf-overflow-y-auto">
      <Card
        size="small"
        title={
          <span>
            <BugOutlined /> {t('ailab.card_anomaly_discovery')}
          </span>
        }
        className="gaf-mb-lg"
      >
        <Space wrap>
          <div>
            <Text strong className="gaf-mb-xs gaf-display-block">
              {t('ailab.label_time_range')}
            </Text>
            <Select
              value={daysRange}
              onChange={setDaysRange}
              className="gaf-w-sm"
              options={[
                { value: 1, label: t('ailab.option_days_1') },
                { value: 3, label: t('ailab.option_days_3') },
                { value: 7, label: t('ailab.option_days_7') },
                { value: 14, label: t('ailab.option_days_14') },
                { value: 30, label: t('ailab.option_days_30') },
              ]}
            />
          </div>
          <div>
            <Text strong className="gaf-mb-xs gaf-display-block">
              {t('ailab.label_min_occurrences')}
            </Text>
            <Select
              value={minOccurrences}
              onChange={setMinOccurrences}
              style={{ width: 140 }}
              options={[
                { value: 2, label: t('ailab.option_min_2') },
                { value: 3, label: t('ailab.option_min_3') },
                { value: 5, label: t('ailab.option_min_5') },
                { value: 10, label: t('ailab.option_min_10') },
              ]}
            />
          </div>
          <div style={{ paddingTop: 20 }}>
            <Button type="primary" icon={<SearchOutlined />} onClick={handleDetect} loading={detecting} size="large">
              {t('ailab.btn_start_detect')}
            </Button>
          </div>
        </Space>
      </Card>

      {detecting && (
        <div className="gaf-text-center" style={{ padding: 40 }}>
          <Spin size="large" description={t('ailab.msg_analyzing_anomaly')} />
        </div>
      )}

      {result && !detecting && (
        <>
          {/* Summary Card */}
          <Card size="small" title={t('ailab.card_analysis_summary')} className="gaf-mb-lg">
            <Paragraph>{result.summary}</Paragraph>
            <Row gutter={16}>
              <Col span={6}>
                <Statistic
                  title={t('ailab.label_analyzed_samples')}
                  value={result.total_analyzed}
                  prefix={<SearchOutlined />}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('ailab.label_failed_count')}
                  value={result.stats?.failed_count || 0}
                  styles={{ content: { color: token.colorError } }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('ailab.label_failure_rate')}
                  value={result.stats?.failure_rate || 0}
                  suffix="%"
                  precision={1}
                />
              </Col>
              <Col span={6}>
                <Statistic title={t('ailab.label_unique_errors')} value={result.stats?.unique_errors || 0} />
              </Col>
            </Row>
          </Card>

          {/* Pattern List */}
          {(result.patterns || []).length > 0 ? (
            <>
              <Card
                size="small"
                title={t('ailab.card_patterns_found', { count: result.patterns.length })}
                className="gaf-mb-lg"
              >
                <Timeline
                  items={(result.patterns || []).map((pattern) => ({
                    color: getSeverityColor(pattern.severity),
                    content: (
                      <div key={pattern.pattern_text} style={{ paddingBottom: 8 }}>
                        <div className="gaf-flex-center gaf-gap-sm" style={{ marginBottom: 6 }}>
                          <Tag
                            color={severityConfig[pattern.severity]?.color}
                            icon={severityConfig[pattern.severity]?.icon}
                          >
                            {severityConfig[pattern.severity]?.labelKey
                              ? t(severityConfig[pattern.severity].labelKey)
                              : pattern.severity}
                          </Tag>
                          <Tag>
                            {CATEGORY_LABELS[pattern.category]
                              ? t(CATEGORY_LABELS[pattern.category])
                              : pattern.category}
                          </Tag>
                          <Text strong>{t('ailab.label_occurrence_count', { count: pattern.occurrence_count })}</Text>
                        </div>
                        <pre
                          className="gaf-m-0 gaf-py-sm gaf-px-md gaf-text-xs gaf-radius-md gaf-font-mono gaf-whitespace-pre-wrap gaf-overflow-auto gaf-word-break"
                          style={{ background: token.colorBgLayout, maxHeight: 80 }}
                        >
                          {pattern.pattern_text}
                        </pre>
                        {(pattern.sample_messages || []).slice(0, 2).map((sample, i) => (
                          <Text
                            key={`sample-${i}-${sample.slice(0, 12)}`}
                            type="secondary"
                            className="gaf-mt-xs gaf-text-xxs gaf-display-block"
                          >
                            {t('ailab.label_sample', { index: i + 1 })}: {sample.slice(0, 120)}
                            {sample.length > 120 ? '...' : ''}
                          </Text>
                        ))}
                      </div>
                    ),
                  }))}
                />
              </Card>

              {/* Severity Distribution */}
              <Card size="small" title={t('ailab.card_severity_distribution')} className="gaf-mb-lg">
                <Row gutter={[16, 8]}>
                  {Object.entries(severityConfig).map(([key, cfg]) => {
                    const count = (result.patterns || []).filter((p) => p.severity === key).length;
                    const pct = result.patterns.length > 0 ? (count / result.patterns.length) * 100 : 0;
                    return (
                      <Col span={6} key={key}>
                        <div className="gaf-text-center">
                          <Progress
                            type="circle"
                            percent={Math.round(pct)}
                            size={64}
                            strokeColor={cfg.color}
                            format={() => count}
                          />
                          <div>
                            <Text strong>{t(cfg.labelKey)}</Text>
                          </div>
                        </div>
                      </Col>
                    );
                  })}
                </Row>
              </Card>

              {/* LLM Analysis */}
              {result.llm_analysis && (
                <Card
                  size="small"
                  title={
                    <span>
                      <ThunderboltOutlined /> {t('ailab.label_ai_analysis_report')}
                    </span>
                  }
                  className="gaf-mb-lg"
                >
                  <div
                    className="gaf-text-sm gaf-p-lg gaf-whitespace-pre-wrap gaf-radius-lg gaf-word-break"
                    style={{ background: token.colorBgLayout, lineHeight: 1.8 }}
                  >
                    {result.llm_analysis}
                  </div>
                </Card>
              )}
            </>
          ) : (
            <Alert
              type="success"
              showIcon
              icon={<CheckCircleOutlined />}
              title={t('ailab.alert_no_anomaly_title')}
              description={t('ailab.alert_no_anomaly_desc')}
              className="gaf-mb-lg"
            />
          )}
        </>
      )}

      {!result && !detecting && <Empty description={t('ailab.empty_set_params')} />}
    </div>
  );
}

export default AnomalyPatternTab;
