import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Select,
  Spin,
  Typography,
  Space,
  Card,
  Timeline,
  Descriptions,
  Alert,
  Tag,
  Tabs,
  App,
  theme as antTheme,
} from 'antd';
import {
  SearchOutlined,
  BugOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  ThunderboltOutlined,
  RobotOutlined,
  PlayCircleOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import { fetchExecutions } from '@/api/tasks';
import { fetchExecutionAnalysis, analyzeExecutionWithAgent, fetchAgentSessionStatus } from '@/api/ai';
import type { AgentAnalysisResult } from '@/api/ai';
import { TrajectoryTimeline } from '@/components/Ai/TrajectoryTimeline';
import { AnomalyPatternTab } from '@/pages/AI/AnomalyPatternPanel';
import { fetchDebugLogs, analyzeDebugLog, fetchAnalysisResults } from '@/api/debug';
import { fetchSkills } from '@/api/skills';
import type { DebugLogArchive, LLMAnalysisResult, AnalysisStatus, SkillDefinition } from '@/types/models';
import { useTranslation } from '@/i18n';
import { PageWrapper } from '@/components/Common/PageWrapper';

const { Text, Paragraph } = Typography;

interface ExecutionRecord {
  id: string;
  task_name: string;
  status: string;
  started_at: string;
  completed_at: string | null;
}

interface LogAnalysisResult {
  steps: Array<{ name: string; status: string; duration_ms: number; error?: string }>;
  summary: string;
  suggestions: string[];
}

/** Execution Analysis tab — analyze execution logs with LLM agent */
function ExecutionAnalysisTab() {
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
  const [selectedExecId, setSelectedExecId] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<LogAnalysisResult | null>(null);

  // Agent deep analysis state
  const [deepAnalyzing, setDeepAnalyzing] = useState(false);
  const [agentResult, setAgentResult] = useState<AgentAnalysisResult | null>(null);

  useEffect(() => {
    loadExecutions();
  }, []);

  const loadExecutions = async () => {
    try {
      const execData = await fetchExecutions({ page_size: 20 });
      const list = execData?.results || [];
      setExecutions(list as unknown as ExecutionRecord[]);
    } catch (err) {
      console.error('Log executions load failed:', err);
    }
  };

  const handleAnalyze = async () => {
    if (!selectedExecId) return;
    setAnalyzing(true);
    setResult(null);
    setAgentResult(null);
    try {
      const data = await fetchExecutionAnalysis(selectedExecId);
      setResult(data);
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : t('ailab.msg_unknown_error');
      const fallback: LogAnalysisResult = {
        steps: [],
        summary: t('ailab.msg_analyze_failed', { message: errMsg }),
        suggestions: [],
      };
      setResult(fallback);
    } finally {
      setAnalyzing(false);
    }
  };

  // Cancel handle for the deep-analysis polling loop — set when polling
  // starts, cleared on completion/unmount so the async loop can bail out.
  const pollCancelRef = useRef<null | (() => void)>(null);

  // Cancel any pending poll loop when the component unmounts
  useEffect(() => {
    return () => {
      if (pollCancelRef.current) pollCancelRef.current();
    };
  }, []);

  const handleDeepAnalyze = async () => {
    if (!selectedExecId) return;
    setDeepAnalyzing(true);
    setAgentResult(null);

    // Polling state — keep refs so cleanup works even if component re-renders
    const pollIntervalMs = 3000;
    const timeoutMs = 5 * 60 * 1000; // 5 minutes max
    const startTime = Date.now();
    let cancelled = false;
    pollCancelRef.current = () => {
      cancelled = true;
    };

    try {
      // 1. Dispatch the async analysis
      const dispatchResult = await analyzeExecutionWithAgent(selectedExecId);
      if (cancelled) return;
      const sessionId = dispatchResult.session_id;

      // 2. Poll until completed/failed or timeout
      while (!cancelled) {
        if (Date.now() - startTime > timeoutMs) {
          throw new Error('Analysis timed out after 5 minutes');
        }
        await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
        if (cancelled) return;

        const status = await fetchAgentSessionStatus(sessionId);
        if (cancelled) return;

        if (status.status === 'completed' || status.status === 'failed') {
          setAgentResult(status);
          break;
        }
        // status === 'pending' | 'running' — keep polling
      }
    } catch (e: unknown) {
      if (cancelled) return;
      const errMsg = e instanceof Error ? e.message : t('ailab.msg_unknown_error');
      setAgentResult({
        session_id: 0,
        status: 'failed',
        model_used: '',
        reasoning_steps: [],
        summary: t('ailab.msg_deep_analyze_failed', { message: errMsg }),
        suggestions: [],
        total_tokens: 0,
        trajectory: [],
        error: errMsg,
      });
    } finally {
      if (!cancelled) setDeepAnalyzing(false);
      pollCancelRef.current = null;
    }
  };

  const totalDuration = result?.steps?.reduce((sum, s) => sum + (s.duration_ms || 0), 0) || 0;
  const errorSteps = result?.steps?.filter((s) => s.status === 'failed') || [];
  const completedSteps = result?.steps?.filter((s) => s.status === 'success') || [];

  return (
    <div className="gaf-p-xl gaf-h-full gaf-overflow-y-auto">
      <Card size="small" className="gaf-mb-lg">
        <Space wrap>
          <Select
            showSearch
            placeholder={t('ailab.placeholder_select_execution')}
            className="gaf-w-360"
            value={selectedExecId}
            onChange={setSelectedExecId}
            filterOption={(input, option) =>
              ((option?.label as string) || '').toLowerCase().includes(input.toLowerCase())
            }
            options={executions.map((ex) => ({
              value: ex.id,
              label: `${ex.task_name || t('ailab.label_unnamed')} (${String(ex.id).slice(0, 8)}...)`,
            }))}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={handleAnalyze}
            loading={analyzing}
            disabled={!selectedExecId}
          >
            {t('ailab.btn_analyze')}
          </Button>
          <Button
            type="default"
            icon={<ThunderboltOutlined />}
            onClick={handleDeepAnalyze}
            loading={deepAnalyzing}
            disabled={!selectedExecId}
            danger
          >
            {t('ailab.btn_deep_analyze')}
          </Button>
        </Space>
      </Card>

      {analyzing && (
        <div className="gaf-text-center" style={{ padding: 40 }}>
          <Spin size="large" description={t('ailab.msg_analyzing_logs')} />
        </div>
      )}

      {deepAnalyzing && (
        <Card size="small" className="gaf-mb-lg" style={{ borderColor: token.colorPrimary }}>
          <div className="gaf-text-center" style={{ padding: 20 }}>
            <Spin size="large" />
            <div className="gaf-mt-md">
              <RobotOutlined className="gaf-text-2xl" style={{ color: token.colorPrimary }} />
              <Text strong className="gaf-ml-sm">
                {t('ailab.msg_deep_analyzing')}
              </Text>
            </div>
          </div>
        </Card>
      )}

      {result && !analyzing && (
        <>
          <Card size="small" title={t('ailab.card_analysis_summary')} className="gaf-mb-lg">
            <Text>{result.summary}</Text>
          </Card>

          <Card size="small" title={t('ailab.card_execution_steps')} className="gaf-mb-lg">
            <Timeline
              items={result.steps.map((step) => ({
                color: step.status === 'failed' ? 'red' : step.status === 'success' ? 'green' : 'blue',
                content: (
                  <div>
                    <Text strong>{step.name}</Text>
                    <br />
                    <Text type="secondary" className="gaf-text-xs">
                      {t('ailab.label_step_duration_status', {
                        duration: (step.duration_ms / 1000).toFixed(2),
                        status: step.status,
                      })}
                    </Text>
                    {step.error && (
                      <div
                        className="gaf-mt-xs gaf-radius-sm"
                        style={{
                          padding: 6,
                          background: token.colorErrorBg,
                          border: `1px solid ${token.colorErrorBorder}`,
                        }}
                      >
                        <Text type="danger" className="gaf-text-xs gaf-whitespace-pre-wrap">
                          {step.error}
                        </Text>
                      </div>
                    )}
                  </div>
                ),
              }))}
            />
          </Card>

          <Card size="small" title={t('ailab.card_statistics')} className="gaf-mb-lg">
            <Descriptions column={3} size="small">
              <Descriptions.Item
                label={
                  <span>
                    <ClockCircleOutlined /> {t('ailab.label_total_duration')}
                  </span>
                }
              >
                {(totalDuration / 1000).toFixed(2)}s
              </Descriptions.Item>
              <Descriptions.Item
                label={<span style={{ color: token.colorSuccess }}>{t('ailab.label_success_steps')}</span>}
              >
                {completedSteps.length}
              </Descriptions.Item>
              <Descriptions.Item
                label={<span style={{ color: token.colorError }}>{t('ailab.label_failed_steps')}</span>}
              >
                {errorSteps.length}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card size="small" title={t('ailab.card_result_display')} className="gaf-mb-lg">
            <pre
              className="gaf-m-0 gaf-p-lg gaf-radius-lg gaf-overflow-y-auto gaf-text-13 gaf-whitespace-pre-wrap gaf-font-mono gaf-word-break"
              style={{ background: token.colorBgLayout, color: token.colorText, maxHeight: 300, lineHeight: 1.5 }}
            >
              {JSON.stringify(result, null, 2)}
            </pre>
          </Card>
        </>
      )}

      {agentResult && !deepAnalyzing && (
        <Card
          size="small"
          title={
            <Space>
              <RobotOutlined style={{ color: token.colorPrimary }} />
              <span>{t('ailab.card_agent_result')}</span>
              <Tag color={agentResult.status === 'completed' ? 'success' : 'error'}>
                {t('ailab.label_agent_status')}: {agentResult.status}
              </Tag>
            </Space>
          }
          className="gaf-mb-lg"
          style={{ borderColor: token.colorPrimaryBorder }}
        >
          {/* Agent meta info */}
          <Descriptions column={3} size="small" className="gaf-mb-md">
            <Descriptions.Item label={t('ailab.label_model_used')}>{agentResult.model_used || '-'}</Descriptions.Item>
            <Descriptions.Item label={t('ailab.label_total_tokens')}>{agentResult.total_tokens}</Descriptions.Item>
            <Descriptions.Item label={t('ailab.label_agent_status')}>{agentResult.status}</Descriptions.Item>
          </Descriptions>

          {/* Error alert */}
          {agentResult.error && <Alert type="error" title={agentResult.error} className="gaf-mb-md" showIcon />}

          {/* Reasoning chain */}
          {agentResult.reasoning_steps.length > 0 ? (
            <Card size="small" type="inner" title={t('ailab.card_reasoning_chain')} className="gaf-mb-md">
              <Timeline
                items={agentResult.reasoning_steps.map((step, idx) => ({
                  color: 'blue',
                  icon: <ThunderboltOutlined className="gaf-text-md" style={{ color: token.colorPrimary }} />,
                  content: (
                    <div key={`step-${idx}`}>
                      <Space className="gaf-mb-xs">
                        <Tag color="blue">Step {idx + 1}</Tag>
                        {step.action && <Tag color="geekblue">{step.action}</Tag>}
                      </Space>
                      {step.thought && (
                        <div className="gaf-mb-xs">
                          <Text type="secondary" className="gaf-text-xs">
                            {t('ailab.label_thought')}:
                          </Text>
                          <Paragraph className="gaf-m-0 gaf-ml-sm" style={{ display: 'inline' }}>
                            {step.thought}
                          </Paragraph>
                        </div>
                      )}
                      {step.action && step.action_input && (
                        <div className="gaf-mb-xs">
                          <Text type="secondary" className="gaf-text-xs">
                            {t('ailab.label_action')}:
                          </Text>
                          <pre
                            className="gaf-m-0 gaf-ml-sm gaf-radius-sm gaf-text-xs"
                            style={{ display: 'inline', background: token.colorBgLayout, padding: '2px 6px' }}
                          >
                            {JSON.stringify(step.action_input)}
                          </pre>
                        </div>
                      )}
                      {step.observation && (
                        <div>
                          <Text type="secondary" className="gaf-text-xs">
                            {t('ailab.label_observation')}:
                          </Text>
                          <pre
                            className="gaf-m-0 gaf-ml-sm gaf-mt-xs gaf-p-sm gaf-radius-sm gaf-overflow-y-auto gaf-text-xs gaf-whitespace-pre-wrap gaf-word-break"
                            style={{ background: token.colorBgLayout, maxHeight: 150 }}
                          >
                            {step.observation}
                          </pre>
                        </div>
                      )}
                    </div>
                  ),
                }))}
              />
            </Card>
          ) : (
            <Alert type="info" title={t('ailab.label_no_reasoning_steps')} className="gaf-mb-md" showIcon />
          )}

          {/* Agent trajectory (Phase 2 observability: nodes/tools/tokens) */}
          <Card size="small" type="inner" title={t('ailab.trajectory_title')} className="gaf-mb-md">
            <TrajectoryTimeline trajectory={agentResult.trajectory ?? []} />
          </Card>

          {/* Agent summary */}
          {agentResult.summary && (
            <Card size="small" type="inner" title={t('ailab.card_analysis_summary')} className="gaf-mb-md">
              <Paragraph className="gaf-whitespace-pre-wrap">{agentResult.summary}</Paragraph>
            </Card>
          )}

          {/* Agent suggestions */}
          {agentResult.suggestions.length > 0 && (
            <Card size="small" type="inner" title={t('ailab.alert_fix_suggestions_title')}>
              <ul className="gaf-m-0 gaf-pl-lg">
                {agentResult.suggestions.map((sug, idx) => (
                  <li key={`sug-${idx}`} className="gaf-mb-xs">
                    <BugOutlined style={{ color: token.colorWarning }} />
                    <Text className="gaf-ml-xs">{sug}</Text>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </Card>
      )}

      {result && !analyzing && errorSteps.length > 0 && !agentResult && !deepAnalyzing && (
        <Card size="small" className="gaf-mb-lg">
          <Alert
            title={t('ailab.alert_fix_suggestions_title')}
            description={
              <div>
                <Text type="secondary">{t('ailab.alert_fix_suggestions_desc')}</Text>
                <br />
                {/* spec 阶段 3.4d: wire onClick to handleDeepAnalyze (LangGraph
                    ReAct Agent). Previously the button had no onClick, making it
                    a dead UI element. */}
                <Button
                  type="default"
                  size="small"
                  icon={<BugOutlined />}
                  className="gaf-mt-sm"
                  onClick={handleDeepAnalyze}
                  disabled={!selectedExecId}
                >
                  {t('ailab.btn_get_fix_suggestions')}
                </Button>
              </div>
            }
            type="warning"
            showIcon
            icon={<WarningOutlined />}
          />
        </Card>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Archive Analysis tab — analyze uploaded log archives with skills
// Migrated from DebugPage (ops/log-analysis) for normalization
// ─────────────────────────────────────────────

const ARCHIVE_STATUS_COLOR: Record<AnalysisStatus, string> = {
  pending: 'default',
  analyzing: 'processing',
  completed: 'success',
  failed: 'error',
};

function ArchiveAnalysisTab() {
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const { message: msg } = App.useApp();
  const [archives, setArchives] = useState<DebugLogArchive[]>([]);
  const [selectedArchiveId, setSelectedArchiveId] = useState<string | null>(null);
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  const [selectedSkillId, setSelectedSkillId] = useState<string | undefined>(undefined);
  const [analyzing, setAnalyzing] = useState(false);
  const [results, setResults] = useState<LLMAnalysisResult[]>([]);

  useEffect(() => {
    loadArchives();
    loadSkills();
  }, []);

  const loadArchives = async () => {
    try {
      const res = await fetchDebugLogs({ page: 1, page_size: 100 });
      setArchives(res.results || []);
    } catch {
      // axios interceptor surfaces the error
    }
  };

  const loadSkills = async () => {
    try {
      const res = await fetchSkills({ page_size: 100 });
      setSkills(res.results || []);
    } catch {
      // skill load failure should not block the page
    }
  };

  const loadResults = async (archiveId: string) => {
    try {
      const data = await fetchAnalysisResults(archiveId);
      setResults(data);
    } catch {
      setResults([]);
    }
  };

  const handleAnalyze = async () => {
    if (!selectedArchiveId) {
      msg.warning(t('debug.msg_select_archive_first'));
      return;
    }
    if (!selectedSkillId) {
      msg.warning(t('debug.msg_select_skill_first'));
      return;
    }
    setAnalyzing(true);
    try {
      await analyzeDebugLog(selectedArchiveId, Number(selectedSkillId));
      msg.success(t('debug.msg_analyze_triggered'));
      // Refresh archive list to show updated status
      await loadArchives();
      await loadResults(selectedArchiveId);
    } catch {
      msg.error(t('debug.msg_analyze_failed'));
    } finally {
      setAnalyzing(false);
    }
  };

  const handleSelectArchive = (archiveId: string) => {
    setSelectedArchiveId(archiveId);
    setResults([]);
    loadResults(archiveId);
  };

  const ARCHIVE_STATUS_LABEL: Record<AnalysisStatus, string> = {
    pending: t('debug.status_pending'),
    analyzing: t('debug.status_analyzing'),
    completed: t('debug.status_completed'),
    failed: t('debug.status_failed'),
  };

  return (
    <div className="gaf-p-xl gaf-h-full gaf-overflow-y-auto">
      <Card size="small" className="gaf-mb-lg">
        <Space wrap>
          <Select
            showSearch
            placeholder={t('debug.placeholder_select_archive')}
            className="gaf-w-360"
            value={selectedArchiveId || undefined}
            onChange={(val) => val && handleSelectArchive(val)}
            filterOption={(input, option) =>
              ((option?.label as string) || '').toLowerCase().includes(input.toLowerCase())
            }
            options={archives.map((a) => ({
              value: a.id,
              label: `${a.zip_file_path?.split(/[\\/]/).pop() || a.id} (${a.analysis_status})`,
            }))}
          />
          <Select
            showSearch
            placeholder={t('debug.placeholder_select_skill')}
            className="gaf-w-200"
            value={selectedSkillId}
            onChange={setSelectedSkillId}
            filterOption={(input, option) =>
              ((option?.label as string) || '').toLowerCase().includes(input.toLowerCase())
            }
            options={skills.map((s) => ({ value: s.id, label: s.name }))}
          />
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleAnalyze}
            loading={analyzing}
            disabled={!selectedArchiveId || !selectedSkillId}
          >
            {t('debug.btn_analyze')}
          </Button>
        </Space>
      </Card>

      {selectedArchiveId && (
        <Card size="small" className="gaf-mb-lg">
          <Descriptions column={2} size="small">
            <Descriptions.Item label={t('debug.col_status')}>
              {archives.find((a) => a.id === selectedArchiveId) && (
                <Tag
                  color={
                    ARCHIVE_STATUS_COLOR[archives.find((a) => a.id === selectedArchiveId)!.analysis_status] || 'default'
                  }
                >
                  {ARCHIVE_STATUS_LABEL[archives.find((a) => a.id === selectedArchiveId)!.analysis_status]}
                </Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label={t('debug.col_created_at')}>
              {archives.find((a) => a.id === selectedArchiveId)?.uploaded_at || '-'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      {analyzing && (
        <div className="gaf-text-center" style={{ padding: 40 }}>
          <Spin size="large" />
        </div>
      )}

      {!analyzing && results.length > 0 && (
        <>
          <Card size="small" title={t('debug.analysis_results_title')} className="gaf-mb-lg">
            {results.map((r) => {
              const tagColor =
                r.review_status === 'adopted'
                  ? 'green'
                  : r.review_status === 'ignored'
                    ? 'red'
                    : r.review_status === 'investigating'
                      ? 'orange'
                      : 'blue';
              const resultText = r.result_data ? JSON.stringify(r.result_data, null, 2) : '';
              const suggestionsText = r.suggestions && r.suggestions.length > 0 ? r.suggestions.join('\n') : '';
              return (
                <div
                  key={r.id}
                  className="gaf-p-md gaf-mb-sm gaf-radius-md"
                  style={{ border: `1px solid ${token.colorBorder}` }}
                >
                  <Space className="gaf-mb-xs">
                    <Tag color={tagColor}>{r.review_status}</Tag>
                    {r.model_name && <Text type="secondary">{r.model_name}</Text>}
                    {r.confidence != null && (
                      <Text type="secondary">
                        {t('debug.confidence_label', { value: (r.confidence * 100).toFixed(1) })}
                      </Text>
                    )}
                  </Space>
                  {resultText && (
                    <pre
                      className="gaf-mt-sm gaf-p-md gaf-radius-md gaf-whitespace-pre-wrap gaf-overflow-auto gaf-text-13 gaf-font-mono"
                      style={{
                        background: token.colorBgLayout,
                        maxHeight: 300,
                      }}
                    >
                      {resultText}
                    </pre>
                  )}
                  {suggestionsText && (
                    <div className="gaf-mt-sm gaf-text-xs" style={{ color: token.colorTextSecondary }}>
                      <strong>{t('debug.suggestions_label')}</strong>
                      {suggestionsText}
                    </div>
                  )}
                </div>
              );
            })}
          </Card>
        </>
      )}

      {!analyzing && selectedArchiveId && results.length === 0 && (
        <Card size="small">
          <div className="gaf-text-center" style={{ padding: 40 }}>
            <FileSearchOutlined style={{ fontSize: 32, color: token.colorTextTertiary }} />
            <div className="gaf-mt-md">
              <Text type="secondary">{t('debug.no_results')}</Text>
            </div>
          </div>
        </Card>
      )}

      {!selectedArchiveId && (
        <Card size="small">
          <div className="gaf-text-center" style={{ padding: 40 }}>
            <FileSearchOutlined style={{ fontSize: 32, color: token.colorTextTertiary }} />
            <div className="gaf-mt-md">
              <Text type="secondary">{t('debug.placeholder_select_archive')}</Text>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

/** LogAnalysisPanel — unified LLM log analysis entry (execution + archive + anomaly) */
export function LogAnalysisPanel() {
  const t = useTranslation();
  const [activeTab, setActiveTab] = useState<'execution' | 'archive' | 'anomaly'>('execution');

  return (
    <PageWrapper>
      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as 'execution' | 'archive' | 'anomaly')}
        items={[
          {
            key: 'execution',
            label: (
              <span>
                <ThunderboltOutlined />
                <span style={{ marginLeft: 6 }}>{t('ailab.tab_execution_analysis')}</span>
              </span>
            ),
            children: <ExecutionAnalysisTab />,
          },
          {
            key: 'archive',
            label: (
              <span>
                <BugOutlined />
                <span style={{ marginLeft: 6 }}>{t('ailab.tab_archive_analysis')}</span>
              </span>
            ),
            children: <ArchiveAnalysisTab />,
          },
          {
            key: 'anomaly',
            label: (
              <span>
                <WarningOutlined />
                <span style={{ marginLeft: 6 }}>{t('ailab.tab_anomaly')}</span>
              </span>
            ),
            children: <AnomalyPatternTab />,
          },
        ]}
      />
    </PageWrapper>
  );
}

export default LogAnalysisPanel;
