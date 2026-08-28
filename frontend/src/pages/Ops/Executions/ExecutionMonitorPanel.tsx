/**
 * execute real-time monitor panel
 * includes screenshot preview,Canvas overlay, log end end, step progress and manual intervention toolbar
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  PauseCircleOutlined,
  PlayCircleOutlined,
  ForwardOutlined,
  CloseCircleOutlined,
  StopOutlined,
  CameraOutlined,
  VerticalAlignBottomOutlined,
  SearchOutlined,
  CloseOutlined,
  ReloadOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import { Button, Input, Tooltip, Tag, App, Modal, Spin, theme } from 'antd';
import { useScreenshotStream } from '@/hooks/useScreenshotStream';
import { useCanvasAnnotation } from '@/hooks/useCanvasAnnotation';
import { useWebSocket } from '@/hooks/useWebSocket';
import { wsClient } from '@/websocket/client';
import GafCanvasOverlay from '@/components/Canvas/GafCanvasOverlay';
import StepProgressBar from '@/components/Pipeline/StepProgressBar';
import NodeDetailDrawer from '@/components/Pipeline/NodeDetailDrawer';
import {
  pauseExecution,
  resumeExecution,
  skipExecutionStep,
  cancelExecution,
  forceFailExecution,
  fetchExecutionReplay,
  retryFromStep,
} from '@/api/executions';
import type { ExecutionReplayFrame } from '@/api/executions';
import type { StepInfo } from '@/components/Pipeline/StepProgressBar';
import type { StepStatus } from '@/types/models';
import type { Annotation } from '@/components/Canvas/GafCanvasOverlay';
import { useTranslation, getLocale } from '@/i18n';
// Task 4.36 (P0-8, 2026-07-28): import resolveErrorMessage for 5 干预操作 catch 块
// (Task 4.22 引入调用但漏 import, 运行时 ReferenceError)
import { resolveErrorMessage } from '@/utils/errorHandler';

/** log record item */
interface LogEntry {
  id: string;
  timestamp: string;
  level: 'INFO' | 'OK' | 'WARN' | 'ERROR';
  message: string;
}

/** ExecutionMonitorPanel props */
interface ExecutionMonitorPanelProps {
  executionId: number;
  agentId?: string;
  steps: StepInfo[];
}

/** log level color mapping */
const LOG_COLORS: Record<string, string> = {
  INFO: '#d4d4d4',
  OK: '#e6db74',
  WARN: '#e6db74',
  ERROR: '#f44747',
};

/** performance threshold value */
const THRESHOLDS = {
  stepDuration: 5000,
  ocrDuration: 500,
  screenshotDuration: 200,
};

/**
 * execute real-time monitor panel component
 */
export function ExecutionMonitorPanel({ executionId, agentId, steps }: ExecutionMonitorPanelProps) {
  const t = useTranslation();
  const { message: antMessage } = App.useApp();
  const { token } = theme.useToken();
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(0);
  const [perfMetrics, setPerfMetrics] = useState({
    currentStepDuration: 0,
    ocrDuration: 0,
    screenshotDuration: 0,
    totalDuration: 0,
  });
  // Local step state — kept in sync with the `steps` prop (REST fetch in
  // parent) and upserted in real time by execution_step_update WS events
  // so the StepProgressBar reflects step transitions without re-fetching.
  const [liveSteps, setLiveSteps] = useState<StepInfo[]>(steps);
  useEffect(() => {
    setLiveSteps(steps);
  }, [steps]);

  // Window background pause state — set to true when the agent sends
  // task.progress with status="paused" reason="window_background", and
  // cleared when status="running" is received (window regained foreground).
  const [windowBgPaused, setWindowBgPaused] = useState(false);

  // N192 B7 P1: 点击 success/failed 步骤跳转对应历史截图帧 (replay 端点)
  const [replayFrame, setReplayFrame] = useState<ExecutionReplayFrame | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);

  // Task 1.1 (B7 重试单节点, P0-1): retry-from-step 确认弹窗 + loading.
  // 仅当存在 failed 步骤时显示"重试此步"按钮; 点击后弹 Modal 二次确认.
  const [retryModalOpen, setRetryModalOpen] = useState(false);
  const [retryLoading, setRetryLoading] = useState(false);
  const [retryTargetStep, setRetryTargetStep] = useState<StepInfo | null>(null);

  // Task 2.4 (N192 B7 P1-7): NodeDetailDrawer 状态.
  // 点击 success/failed 步骤 → 同时打开截图 Modal + 节点详情 Drawer,
  // 让用户能查到 "这个节点当时配的 threshold/ROI 是多少" 而不必找开发查日志.
  const [nodeDetailOpen, setNodeDetailOpen] = useState(false);
  const [nodeDetailStep, setNodeDetailStep] = useState<StepInfo | null>(null);

  const logContainerRef = useRef<HTMLDivElement>(null);
  const logIdCounter = useRef(0);

  const { currentFrame, isStreaming, startStream, stopStream } = useScreenshotStream();
  const { annotations, addAnnotation, clearAnnotations } = useCanvasAnnotation();

  /** handle execute log message */
  const handleExecutionLog = useCallback((data: Record<string, unknown>) => {
    const entry: LogEntry = {
      id: `log_${++logIdCounter.current}`,
      timestamp: (data.timestamp as string) || new Date().toISOString(),
      level: (data.level as LogEntry['level']) || 'INFO',
      message: (data.message as string) || JSON.stringify(data),
    };

    // Track window background pause/resume state from task.progress frames
    // forwarded by the backend as execution_log events with status/reason.
    const logStatus = data.status as string | undefined;
    const logReason = data.reason as string | undefined;
    if (logStatus === 'paused' && logReason === 'window_background') {
      setWindowBgPaused(true);
    } else if (logStatus === 'running') {
      setWindowBgPaused(false);
    }

    // Defensive deduplication: stale channel-layer memberships (common in the
    // dev InMemoryChannelLayer after abrupt browser disconnects) can deliver the
    // same execution_log frame multiple times. Drop a consecutive duplicate that
    // matches at second-level granularity so the terminal stays readable without
    // hiding unrelated repeated messages.
    setLogEntries((prev) => {
      const last = prev[prev.length - 1];
      if (
        last &&
        formatTimestamp(last.timestamp) === formatTimestamp(entry.timestamp) &&
        last.level === entry.level &&
        last.message === entry.message
      ) {
        return prev;
      }
      return [...prev.slice(-500), entry];
    });

    const currentStep = data.current_step_index as number | undefined;
    if (currentStep !== undefined) {
      setCurrentStepIndex(currentStep);
    }

    if (data.perf) {
      const perf = data.perf as Record<string, number>;
      setPerfMetrics((prev) => ({
        ...prev,
        ...perf,
      }));
    }
  }, []);

  useWebSocket('execution_log', handleExecutionLog);

  /** Seed the log terminal with cached execution_log events that arrived before
   *  this panel mounted. Without this, opening the monitor for a finished
   *  execution shows an empty log terminal even though the backend forwarded
   *  the logs. */
  useEffect(() => {
    const cached = wsClient.getCachedExecutionLogs(executionId);
    if (cached.length > 0) {
      setLogEntries(
        cached.map((entry) => ({
          id: `log_${++logIdCounter.current}`,
          timestamp: entry.timestamp,
          level: (entry.level as LogEntry['level']) || 'INFO',
          message: entry.message,
        })),
      );
    }
  }, [executionId]);

  /** upsert step status from execution_step_update WS events (P3-2).
   *  The backend ExecutionStep post_save signal pushes {step_index, status,
   *  duration_ms, ...} so we can update the StepProgressBar in real time
   *  without re-fetching the steps endpoint. Only events for the execution
   *  currently being monitored are applied. */
  const handleStepUpdate = useCallback(
    (data: Record<string, unknown>) => {
      const eventExecutionId = Number(data.execution_id);
      if (eventExecutionId !== executionId) return;
      const stepIndex = Number(data.step_index);
      if (Number.isNaN(stepIndex)) return;
      const status = data.status as StepStatus | undefined;
      if (!status) return;
      const durationMs = data.duration_ms != null ? Number(data.duration_ms) : undefined;
      const name = (data.step_name as string | undefined) ?? `step_${stepIndex}`;
      // N192 B6 P0: 提取 error_message (后端可能用 error_message 或 error_msg 字段名)
      const errorMessage = (data.error_message as string | undefined) ?? (data.error_msg as string | undefined);
      // Task 3.6 (P2-6): 提取 error_code (NO_MATCH/TIMEOUT/...), 与 agent
      // AutoResult.error_code 对齐。前端 StepProgressBar 按 error.codes.<CODE>
      // 映射多语言文案 (N192 B1/B2), 而非把后端中文 error_message 原文甩给多语言用户。
      const errorCode = (data.error_code as string | undefined) ?? (data.errorCode as string | undefined);
      setLiveSteps((prev) => {
        const idx = prev.findIndex((s) => s.index === stepIndex);
        const updated: StepInfo = {
          index: stepIndex,
          name,
          status,
          duration: durationMs,
          // 只在 failed 状态时保留 error_message, 其他状态清空
          error_message: status === 'failed' ? errorMessage : undefined,
          // Task 3.6: 同样只在 failed 状态时保留 error_code
          error_code: status === 'failed' ? errorCode : undefined,
        };
        if (idx === -1) {
          // New step — append in index order.
          const next = [...prev, updated];
          next.sort((a, b) => a.index - b.index);
          return next;
        }
        const next = [...prev];
        next[idx] = { ...next[idx], ...updated };
        return next;
      });
      // Advance the current step pointer when a step is running so the
      // StepProgressBar highlights the active step.
      if (status === 'running') {
        setCurrentStepIndex(stepIndex);
      }
    },
    [executionId],
  );

  useWebSocket('execution_step_update', handleStepUpdate);

  /** N192 B7 P1: 点击 success/failed 步骤 → 调用 replay 端点拿历史帧, Modal 展示对应截图.
   *  对进行中执行可能尚无帧, 用户友好提示而非静默失败 (spec issue #5).
   *
   *  Task 2.4 (N192 B7 P1-7): 同时打开 NodeDetailDrawer, 让用户能查到
   *  "这个节点当时配的 threshold/ROI 是多少" 而不必找开发查日志. */
  const handleStepClick = useCallback(
    async (step: StepInfo) => {
      // Task 2.4: 同时打开 NodeDetailDrawer (即使 replay 无截图, 节点详情也能看)
      setNodeDetailStep(step);
      setNodeDetailOpen(true);

      setReplayLoading(true);
      try {
        const replay = await fetchExecutionReplay(executionId);
        const frames = replay.frames || [];
        if (frames.length === 0) {
          antMessage.info(t('executions.replay_no_frames'));
          return;
        }
        // 找到匹配 stepIndex 的第一帧 (该 step 最早截图; 一个 step 可能有 frameStart/frameEnd 多帧)
        const frame = frames.find((f) => f.stepIndex === step.index);
        if (frame) {
          setReplayFrame(frame);
        } else {
          antMessage.info(t('executions.replay_no_frame_for_step'));
        }
      } catch (error) {
        console.warn('Failed to fetch replay:', error);
        antMessage.error(t('executions.replay_fetch_failed'));
      } finally {
        setReplayLoading(false);
      }
    },
    [executionId, antMessage, t],
  );

  /** Task 2.4: 单独打开节点详情 Drawer (用于截图 Modal 中的"查看节点详情"按钮,
   *  当用户已经看到截图但想再看 input_config / threshold / ROI 时使用). */
  const handleOpenNodeDetail = useCallback((step: StepInfo) => {
    setNodeDetailStep(step);
    setNodeDetailOpen(true);
  }, []);

  /** Task 1.1 (B7 重试单节点, P0-1): 打开"重试此步"确认弹窗.
   *  找到第一个 failed 步骤作为默认重试目标; 若无 failed 步骤则提示.
   *  N192 B7: 用户拿到错误后能自行修复 (重试此步) 而不必重跑整个 pipeline. */
  const handleRetryFromStep = useCallback(() => {
    const firstFailed = liveSteps.find((s) => s.status === 'failed');
    if (!firstFailed) {
      antMessage.info(t('executions.tooltip_retry_step'));
      return;
    }
    setRetryTargetStep(firstFailed);
    setRetryModalOpen(true);
  }, [liveSteps, antMessage, t]);

  /** Task 1.1: 确认重试 → 调用 retry-from-step API.
   *  成功后提示新 execution id (用户可去执行列表查看新执行); 失败展示后端 message. */
  const handleRetryConfirm = useCallback(async () => {
    if (!retryTargetStep) return;
    setRetryLoading(true);
    try {
      const result = await retryFromStep(executionId, retryTargetStep.index);
      antMessage.success(t('executions.msg_retry_success', { id: result.new_execution_id }));
      setRetryModalOpen(false);
    } catch (error) {
      // N192 B1: 后端返回 unified_response {code, message, data},
      // axios interceptor 已把非零 code 转为 reject; error.response?.data
      // 携带 message 字段, 直接展示给用户 (可读文案, 非原始异常).
      const errData = (error as { response?: { data?: { message?: string } } }).response?.data;
      const errMsg = errData?.message || (error as Error).message || 'unknown';
      antMessage.error(t('executions.msg_retry_failed', { message: errMsg }));
    } finally {
      setRetryLoading(false);
    }
  }, [executionId, retryTargetStep, antMessage, t]);

  /** start / stop screenshot stream */
  useEffect(() => {
    if (agentId) {
      startStream(agentId);
      return () => stopStream();
    }
    return undefined;
  }, [agentId, startStream, stopStream]);

  /** based on log update annotation */
  useEffect(() => {
    clearAnnotations();
    const lastLog = logEntries[logEntries.length - 1];
    if (!lastLog) return;

    if (lastLog.message.includes('match')) {
      addAnnotation({
        type: 'rect',
        x: 50,
        y: 50,
        width: 100,
        height: 80,
        color: token.colorSuccess,
        label: t('executions.annotation_template_match'),
      });
    }
    if (lastLog.message.includes('click')) {
      const match = lastLog.message.match(/\((\d+),\s*(\d+)\)/);
      if (match) {
        addAnnotation({
          type: 'circle',
          x: Number(match[1]) - 8,
          y: Number(match[2]) - 8,
          width: 16,
          height: 16,
          color: token.colorError,
          label: t('executions.annotation_click'),
        });
      }
    }
  }, [logEntries, addAnnotation, clearAnnotations, t]);

  /** auto scroll to bottom */
  useEffect(() => {
    if (!autoScroll || !logContainerRef.current) return;
    const el = logContainerRef.current;
    el.scrollTop = el.scrollHeight;
  }, [logEntries, autoScroll]);

  /** Escape HTML special characters to prevent XSS when inserting into dangerouslySetInnerHTML */
  const escapeHtml = useCallback((text: string): string => {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }, []);

  /** Highlight search keyword; input is HTML-escaped first to prevent XSS */
  const highlightKeyword = useCallback(
    (text: string): string => {
      const escaped = escapeHtml(text);
      if (!searchKeyword) return escaped;
      return escaped.replace(
        new RegExp(`(${searchKeyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'),
        '<mark style="background:#ff0;color:#000;padding:0 2px">$1</mark>',
      );
    },
    [searchKeyword, escapeHtml],
  );

  /** format transform time timestamp */
  const formatTimestamp = (ts: string): string => {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString(getLocale(), { hour12: false });
    } catch {
      return ts;
    }
  };

  /** screenshot area annotation data mapping */
  const canvasAnnotations: Annotation[] = useMemo(
    () =>
      annotations.map((a) => ({
        id: a.id,
        type: a.type,
        x: a.x,
        y: a.y,
        width: a.width,
        height: a.height,
        color: a.color,
        label: a.label,
      })),
    [annotations],
  );

  /** TD-335 spec-134: button operation — 替代静默 catch，加错误提示 */
  // Task 4.22 (P2-17, 2026-07-28): 5 个干预操作改用 resolveErrorMessage,
  // 与 handleRetryConfirm 一致. 原来用通用 msg_action_failed, 用户不知道
  // 是"暂停失败"还是"取消失败", 无法定位原因.
  const handlePause = async () => {
    try {
      await pauseExecution(executionId);
    } catch (error) {
      antMessage.error(resolveErrorMessage(error));
    }
  };
  const handleResume = async () => {
    try {
      await resumeExecution(executionId);
    } catch (error) {
      antMessage.error(resolveErrorMessage(error));
    }
  };
  const handleSkip = async () => {
    try {
      await skipExecutionStep(executionId, String(currentStepIndex));
    } catch (error) {
      antMessage.error(resolveErrorMessage(error));
    }
  };
  const handleForceFail = async () => {
    try {
      await forceFailExecution(executionId);
    } catch (error) {
      antMessage.error(resolveErrorMessage(error));
    }
  };
  const handleCancel = async () => {
    try {
      await cancelExecution(executionId);
    } catch (error) {
      antMessage.error(resolveErrorMessage(error));
    }
  };
  const handleScreenshot = () => {
    if (!currentFrame) return;
    // Auto-detect MIME from base64 header: JPEG starts with /9j/, PNG with iVBOR
    const isJpeg = currentFrame.imageBase64.startsWith('/9j/');
    const mime = isJpeg ? 'image/jpeg' : 'image/png';
    const ext = isJpeg ? 'jpg' : 'png';
    const link = document.createElement('a');
    link.href = `data:${mime};base64,${currentFrame.imageBase64}`;
    link.download = `screenshot_${Date.now()}.${ext}`;
    link.click();
  };

  return (
    <div
      className="gaf-mt-lg"
      style={{ border: `1px solid ${token.colorBorder}`, borderRadius: token.borderRadius, overflow: 'hidden' }}
    >
      <div
        className="gaf-toolbar"
        style={{ background: token.colorBgLayout, borderBottom: `1px solid ${token.colorBorderSecondary}` }}
      >
        <div className="gaf-toolbar-group">
          <Tooltip title={t('executions.tooltip_pause')}>
            <Button
              size="small"
              icon={<PauseCircleOutlined />}
              style={{ color: token.colorSuccess, borderColor: token.colorSuccess }}
              onClick={handlePause}
            >
              {t('executions.btn_pause')}
            </Button>
          </Tooltip>
          <Tooltip title={t('executions.tooltip_resume')}>
            <Button
              size="small"
              icon={<PlayCircleOutlined />}
              style={{ color: token.colorPrimary, borderColor: token.colorPrimary }}
              onClick={handleResume}
            >
              {t('executions.btn_continue')}
            </Button>
          </Tooltip>
          <Tooltip title={t('executions.tooltip_skip_current_step')}>
            <Button
              size="small"
              icon={<ForwardOutlined />}
              style={{ color: token.colorWarning, borderColor: token.colorWarning }}
              onClick={handleSkip}
            >
              {t('executions.btn_skip')}
            </Button>
          </Tooltip>
          <Tooltip title={t('executions.tooltip_force_fail')}>
            <Button size="small" icon={<CloseCircleOutlined />} danger onClick={handleForceFail}>
              {t('executions.tooltip_force_fail')}
            </Button>
          </Tooltip>
          <Tooltip title={t('executions.tooltip_cancel')}>
            <Button size="small" icon={<StopOutlined />} danger type="primary" onClick={handleCancel}>
              {t('executions.btn_cancel')}
            </Button>
          </Tooltip>
          <Tooltip title={t('executions.tooltip_screenshot_save')}>
            <Button size="small" icon={<CameraOutlined />} onClick={handleScreenshot}>
              {t('executions.btn_screenshot')}
            </Button>
          </Tooltip>
          {liveSteps.some((s) => s.status === 'failed') && (
            <Tooltip title={t('executions.tooltip_retry_step')}>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                style={{ color: token.colorPrimary, borderColor: token.colorPrimary }}
                onClick={handleRetryFromStep}
              >
                {t('executions.btn_retry_step')}
              </Button>
            </Tooltip>
          )}
          {windowBgPaused && (
            <Tag color="gold" icon={<PauseCircleOutlined />} style={{ marginInlineEnd: 0 }}>
              {t('executions.window_background_paused')}
            </Tag>
          )}
        </div>
      </div>

      <div className="gaf-flex" style={{ height: 420, borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
        <div
          className="gaf-position-relative gaf-overflow-hidden"
          style={{ width: '50%', borderRight: `1px solid ${token.colorBorderSecondary}`, background: '#000' }}
        >
          {!agentId ? (
            <div
              className="gaf-flex gaf-flex-center gaf-justify-center gaf-text-sm gaf-h-full"
              style={{ color: token.colorTextSecondary }}
            >
              {t('executions.text_waiting_agent')}
            </div>
          ) : currentFrame ? (
            <div className="gaf-flex gaf-flex-center gaf-justify-center gaf-w-full gaf-h-full">
              <GafCanvasOverlay
                width={currentFrame.width}
                height={currentFrame.height}
                imageBase64={currentFrame.imageBase64}
                annotations={canvasAnnotations}
                style={{
                  maxWidth: '100%',
                  maxHeight: '100%',
                  width: '100%',
                  height: '100%',
                  objectFit: 'contain',
                  border: 'none',
                  borderRadius: 0,
                }}
              />
            </div>
          ) : (
            <div
              className="gaf-flex-col gaf-gap-sm gaf-justify-center gaf-text-sm gaf-h-full"
              style={{ alignItems: 'center', color: '#bbb' }}
            >
              {isStreaming ? t('executions.text_waiting_screenshot') : t('executions.text_screenshot_not_started')}
            </div>
          )}
        </div>

        <div className="gaf-terminal" style={{ width: '50%' }}>
          <div className="gaf-terminal-toolbar">
            <span className="gaf-terminal-toolbar-label">{t('executions.text_log_terminal')}</span>
            <div className="gaf-toolbar-group">
              <Input
                size="small"
                className="gaf-terminal-input"
                placeholder={t('executions.placeholder_search')}
                prefix={<SearchOutlined style={{ color: '#888' }} />}
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
                allowClear={{ clearIcon: <CloseOutlined style={{ color: '#888' }} /> }}
              />
              <Tooltip
                title={
                  autoScroll ? t('executions.tooltip_disable_autoscroll') : t('executions.tooltip_enable_autoscroll')
                }
              >
                <Button
                  size="small"
                  type={autoScroll ? 'primary' : 'default'}
                  icon={<VerticalAlignBottomOutlined />}
                  aria-label={
                    autoScroll ? t('executions.tooltip_disable_autoscroll') : t('executions.tooltip_enable_autoscroll')
                  }
                  onClick={() => setAutoScroll(!autoScroll)}
                  className={autoScroll ? '' : 'gaf-terminal-btn-quiet'}
                />
              </Tooltip>
            </div>
          </div>
          <div ref={logContainerRef} className="gaf-terminal-log">
            {logEntries.length === 0 && (
              <div className="gaf-terminal-log-empty">{t('executions.text_waiting_logs')}</div>
            )}
            {logEntries.map((entry) => (
              <div key={entry.id} className="gaf-terminal-log-entry">
                <span className="gaf-terminal-log-time">{formatTimestamp(entry.timestamp)}</span>
                <span
                  className={`gaf-terminal-log-level ${entry.level === 'ERROR' ? 'gaf-terminal-log-level-error' : ''}`}
                  style={{ color: LOG_COLORS[entry.level] || '#d4d4d4' }}
                >
                  [{entry.level}]
                </span>
                <span
                  dangerouslySetInnerHTML={{
                    __html: highlightKeyword(entry.message),
                  }}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      {liveSteps.length > 0 && (
        <div
          className="gaf-py-sm gaf-px-lg"
          style={{ borderBottom: `1px solid ${token.colorBorderSecondary}`, background: token.colorBgContainer }}
        >
          <div className="gaf-toolbar-group">
            <span className="gaf-font-semibold gaf-text-13" style={{ color: token.colorText }}>
              {t('executions.text_step_progress')}
            </span>
            <span className="gaf-text-xxs" style={{ color: token.colorTextSecondary }}>
              {liveSteps.filter((s) => s.status === 'success').length}/{liveSteps.length}{' '}
              {t('executions.text_step_completed')}
            </span>
          </div>
          <StepProgressBar steps={liveSteps} currentStepIndex={currentStepIndex} onStepClick={handleStepClick} />
        </div>
      )}

      <div
        className="gaf-toolbar gaf-text-xs"
        style={{ padding: '6px 16px', background: token.colorBgLayout, color: token.colorTextTertiary }}
      >
        <span>
          {t('executions.text_current_step')}{' '}
          <span
            className="gaf-font-medium"
            style={{
              color: perfMetrics.currentStepDuration > THRESHOLDS.stepDuration ? token.colorError : token.colorText,
            }}
          >
            {(perfMetrics.currentStepDuration / 1000).toFixed(1)}s
          </span>
        </span>
        <span>
          OCR{' '}
          <span
            className="gaf-font-medium"
            style={{ color: perfMetrics.ocrDuration > THRESHOLDS.ocrDuration ? token.colorError : token.colorText }}
          >
            {perfMetrics.ocrDuration}ms
          </span>
        </span>
        <span>
          {t('executions.text_screenshot')}{' '}
          <span
            className="gaf-font-medium"
            style={{
              color:
                perfMetrics.screenshotDuration > THRESHOLDS.screenshotDuration ? token.colorError : token.colorText,
            }}
          >
            {perfMetrics.screenshotDuration}ms
          </span>
        </span>
        <span>
          {t('executions.text_total_duration')}{' '}
          <span className="gaf-font-medium" style={{ color: token.colorText }}>
            {(perfMetrics.totalDuration / 1000).toFixed(1)}s
          </span>
        </span>
      </div>

      {/* N192 B7 P1: 步骤截图回放 Modal — 点击 success/failed 步骤跳转对应历史帧.
          Task 2.4 (N192 B7 P1-7): Modal 内加 "查看节点详情" 按钮, 让用户能
          打开 NodeDetailDrawer 看节点 input_config / threshold / ROI 等诊断字段. */}
      <Modal
        title={t('executions.replay_frame_modal_title')}
        open={!!replayFrame || replayLoading}
        onCancel={() => setReplayFrame(null)}
        footer={
          replayFrame && nodeDetailStep ? (
            <Button icon={<FileSearchOutlined />} onClick={() => handleOpenNodeDetail(nodeDetailStep)}>
              {t('executions.btn_view_node_detail')}
            </Button>
          ) : null
        }
        width={800}
        destroyOnClose
      >
        {replayLoading ? (
          <div className="gaf-flex gaf-flex-center gaf-justify-center" style={{ padding: 40 }}>
            <Spin />
          </div>
        ) : replayFrame ? (
          <div>
            <div className="gaf-mb-sm" style={{ color: '#666', fontSize: 12 }}>
              {t('executions.replay_frame_step')}: {replayFrame.stepIndex} | {replayFrame.timestamp}
            </div>
            <img
              src={`data:image/png;base64,${replayFrame.imageBase64}`}
              alt={`Step ${replayFrame.stepIndex} screenshot`}
              style={{ maxWidth: '100%', height: 'auto' }}
            />
          </div>
        ) : null}
      </Modal>

      {/* Task 2.4 (N192 B7 P1-7): 节点详情抽屉 — 展示 input_config / 前驱 result_data
          / error_msg / error_code / confidence / threshold / ROI 等诊断字段,
          让用户拿到错误后能自行查到 "这个节点当时配的 threshold/ROI 是多少" 而不必
          找开发查日志. */}
      <NodeDetailDrawer
        open={nodeDetailOpen}
        executionId={executionId}
        stepIndex={nodeDetailStep?.index ?? 0}
        stepName={nodeDetailStep?.name}
        onClose={() => setNodeDetailOpen(false)}
      />

      {/* Task 1.1 (B7 重试单节点, P0-1): 重试确认弹窗.
          N192 B7: 用户能自行从失败步骤重试, 不必重跑整个 pipeline.
          N192 B1: 错误提示归一 — 后端返回可读 message, 前端原样展示.
          N192 B3: 弹窗展示失败原因 (error_message), 让用户知道 WHY 失败
            而非只看到 step_index — 满足 B3「第几个节点 / 哪个字段 / 为什么不合法」. */}
      <Modal
        title={t('executions.tooltip_retry_step')}
        open={retryModalOpen}
        onOk={handleRetryConfirm}
        onCancel={() => setRetryModalOpen(false)}
        confirmLoading={retryLoading}
        okText={t('executions.btn_retry_step')}
        cancelText={t('executions.modal_cancel')}
        destroyOnClose
      >
        {retryTargetStep && (
          <div>
            <p>
              {t('executions.modal_retry_confirm', {
                id: executionId,
                stepIndex: retryTargetStep.index,
              })}
            </p>
            {retryTargetStep.error_message && (
              <p style={{ color: token.colorError, marginTop: 8 }}>
                {t('executions.modal_retry_failure_reason', {
                  reason: retryTargetStep.error_message,
                })}
              </p>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

export default ExecutionMonitorPanel;
