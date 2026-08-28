/**
 * Task 2.4 (N192 B7 P1-7): 节点详情抽屉组件.
 *
 * 在执行监控面板上点击节点时弹出, 展示节点的完整诊断上下文:
 *   - 基本信息 (id / type / step_index / 耗时 / 状态)
 *   - 节点 input_config (JSON 视图, 可折叠/展开, 大 config 截断显示)
 *   - 前驱节点 result_data 摘要 (JSON 视图)
 *   - 当前节点诊断字段 (confidence / threshold / match_location / roi / screenshot_path)
 *   - 失败时的 error_msg + error_code (高亮展示)
 *   - 节点设计语义 (comment / rationale — spec 阶段 4.3)
 *
 * N192 B7 复现路径: 用户拿到 "模板未找到: tpl_001" 后, 可在 Drawer 看到
 * "这个节点当时配的 threshold 是多少? ROI 是什么?" 而不必找开发查日志.
 *
 * N192 B3 错误定位: Drawer 展示节点 id + 错误码 + 错误信息 + input_config,
 * 让用户知道 "第几个节点 / 哪个字段 / 什么输入 / 为什么不合法".
 */
import { useEffect, useState, useCallback } from 'react';
import { App, Drawer, Typography, Card, Tag, Spin, Empty, Alert, Button, Tooltip, theme } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  CopyOutlined,
  ExpandAltOutlined,
  CompressOutlined,
} from '@ant-design/icons';
import type { NodeTraceData } from '@/api/tasks';
import { getNodeTrace } from '@/api/tasks';
import { useTranslation } from '@/i18n';

const { Text, Paragraph, Title } = Typography;

/** NodeDetailDrawer props */
interface NodeDetailDrawerProps {
  /** 是否显示 */
  open: boolean;
  /** 执行 ID */
  executionId: number;
  /** 步骤序号 (0-based) */
  stepIndex: number;
  /** 步骤名称 (来自 TaskStep, 用于 Drawer 标题展示, 不传则用 step_index) */
  stepName?: string;
  /** 关闭回调 */
  onClose: () => void;
}

/** JSON 字符串截断阈值 — 超过此长度的 config 在折叠状态下截断显示 */
const JSON_TRUNCATE_THRESHOLD = 800;

/** JSON 视图块 (Card 内的可折叠 JSON 展示) */
interface JsonBlockProps {
  /** 区块标题 */
  title: string;
  /** JSON 数据 (null/undefined → 显示 "无") */
  data: unknown;
  /** 主题 token */
  token: ReturnType<typeof theme.useToken>['token'];
  /** 默认是否展开 (大 config 默认折叠) */
  defaultExpanded?: boolean;
}

/** JsonBlock: 可折叠的 JSON 视图块, 大对象自动截断. */
function JsonBlock({ title, data, token, defaultExpanded = false }: JsonBlockProps) {
  const t = useTranslation();
  const [expanded, setExpanded] = useState(defaultExpanded);

  // data 为 null/undefined/空对象/空数组 → 显示 "无"
  const isEmpty = data == null || (typeof data === 'object' && Object.keys(data as object).length === 0);

  if (isEmpty) {
    return (
      <Card size="small" title={title} style={{ marginBottom: 8 }}>
        <Text type="secondary">{t('executions.node_detail_empty')}</Text>
      </Card>
    );
  }

  // 序列化 JSON, 截断大对象
  const fullStr = JSON.stringify(data, null, 2);
  const isLong = fullStr.length > JSON_TRUNCATE_THRESHOLD;
  // 折叠状态下显示截断字符串 + "...(N chars)"
  const displayStr =
    expanded || !isLong
      ? fullStr
      : fullStr.slice(0, JSON_TRUNCATE_THRESHOLD) +
        `\n...(${t('executions.node_detail_truncated', { count: fullStr.length - JSON_TRUNCATE_THRESHOLD })})`;

  return (
    <Card
      size="small"
      title={title}
      style={{ marginBottom: 8 }}
      extra={
        <div className="gaf-toolbar-group">
          {/* 复制按钮: 让用户能复制 JSON 到剪贴板, 用于反馈/工单 */}
          <Tooltip title={t('executions.node_detail_copy')}>
            <Button
              size="small"
              type="text"
              icon={<CopyOutlined />}
              onClick={() => {
                navigator.clipboard?.writeText(fullStr).catch(() => {});
              }}
            />
          </Tooltip>
          {/* 展开/折叠按钮: 大对象才显示 */}
          {isLong && (
            <Tooltip title={expanded ? t('executions.node_detail_collapse') : t('executions.node_detail_expand')}>
              <Button
                size="small"
                type="text"
                icon={expanded ? <CompressOutlined /> : <ExpandAltOutlined />}
                onClick={() => setExpanded(!expanded)}
              />
            </Tooltip>
          )}
        </div>
      }
    >
      <pre
        className="gaf-m-0 gaf-text-xs"
        style={{
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          background: token.colorBgLayout,
          padding: 8,
          borderRadius: token.borderRadius,
          maxHeight: expanded ? 'none' : 240,
          overflow: expanded ? 'visible' : 'auto',
        }}
      >
        {displayStr}
      </pre>
    </Card>
  );
}

/** NodeDetailDrawer: 节点详情抽屉 */
export function NodeDetailDrawer({ open, executionId, stepIndex, stepName, onClose }: NodeDetailDrawerProps) {
  const t = useTranslation();
  // Task 4.59 (P1-39, 2026-07-28): 复制诊断信息按钮. 用 App.useApp() 拿 message API
  // (antd 5.x 推荐方式, 与 ExecutionMonitorPanel.tsx:80 一致), 静态 message 不消费 ConfigProvider 上下文.
  const { message: antMessage } = App.useApp();
  const { token } = theme.useToken();
  const [loading, setLoading] = useState(false);
  const [trace, setTrace] = useState<NodeTraceData | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>('');

  /** 拉取节点 trace 数据.
   * 失败时设置 errorMsg (来自 axios businessMessage 或后端 message 字段),
   *  让用户看到 "未找到结构化日志文件 — agent 与 backend 不在同一机器" 等可读提示
   *  (N192 B1 错误提示归一). */
  const fetchTrace = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    setErrorMsg('');
    setTrace(null);
    try {
      const data = await getNodeTrace(executionId, stepIndex);
      setTrace(data);
    } catch (err) {
      // axios 拦截器 reject 时携带 businessMessage (来自统一响应 message 字段).
      // Task 4.21 (P2-16, 2026-07-28): fallback 改用 i18n, 原来用英文
      // 'unknown error' 未走 i18n, 多语言用户看不懂.
      const errObj = err as { businessMessage?: string; message?: string };
      const msg = errObj.businessMessage || errObj.message || t('error.unknown');
      setErrorMsg(msg);
    } finally {
      setLoading(false);
    }
  }, [open, executionId, stepIndex]);

  useEffect(() => {
    if (open) {
      fetchTrace();
    }
  }, [open, fetchTrace]);

  /** Task 4.59 (P1-39, 2026-07-28): 复制诊断信息到剪贴板, markdown 格式.
   * 字段值若是 undefined/null/空字符串则跳过该行 (避免 markdown 出现 "field: " 空值行).
   * input_config 用 JSON.stringify 格式化 (单行, 便于粘贴到工单/IM).
   * N192 B7 复现路径: 用户拿到错误后, 可一键复制完整诊断上下文反馈给开发,
   *   而非截图 + 手动抄字段. */
  const handleCopyDiagnosis = useCallback(() => {
    if (!trace) return;
    const lines: string[] = ['## 节点诊断信息'];
    const pushLine = (label: string, value: unknown) => {
      // 跳过 undefined / null / 空字符串 (0 / false 等 falsy 但有意义的值保留)
      if (value === undefined || value === null || value === '') return;
      lines.push(`- ${label}: ${value}`);
    };
    pushLine('step_index', trace.step_index);
    pushLine('node_id', trace.node_id);
    pushLine('node_type', trace.node_type);
    pushLine('error_code', trace.error_code);
    pushLine('error_msg', trace.error_msg);
    pushLine('confidence', trace.confidence);
    pushLine('threshold', trace.threshold);
    pushLine('coord_system', trace.coord_system);
    if (trace.input_config !== null && trace.input_config !== undefined) {
      pushLine('input_config', JSON.stringify(trace.input_config));
    }
    const text = lines.join('\n');
    navigator.clipboard?.writeText(text).then(
      () => antMessage.success(t('msg_copy_success')),
      () => {
        /* 剪贴板被禁用, 静默失败; 用户可手动选中 JSON 块复制 */
      },
    );
  }, [trace, antMessage, t]);

  /** 渲染状态标签 */
  const renderStatusTag = (success: boolean | null) => {
    if (success === null) {
      return <Tag color="default">{t('executions.node_detail_status_unknown')}</Tag>;
    }
    if (success) {
      return (
        <Tag color="success" icon={<CheckCircleOutlined />}>
          {t('executions.step_status_success')}
        </Tag>
      );
    }
    return (
      <Tag color="error" icon={<CloseCircleOutlined />}>
        {t('executions.step_status_failed')}
      </Tag>
    );
  };

  return (
    <Drawer
      title={
        <div className="gaf-flex" style={{ alignItems: 'center', gap: 8 }}>
          <span>
            {t('executions.node_detail_title', {
              step: stepName ?? stepIndex,
            })}
          </span>
          {/* 刷新按钮: 让用户在执行过程中也能重新拉 trace (执行未完成时 JSONL 还在写) */}
          <Tooltip title={t('executions.node_detail_refresh')}>
            <Button size="small" type="text" icon={<ReloadOutlined />} onClick={fetchTrace} loading={loading} />
          </Tooltip>
          {/* Task 4.59 (P1-39, 2026-07-28): 复制诊断信息按钮.
              一键复制 markdown 格式诊断信息 (step_index/node_id/error_code/input_config/...),
              让用户能反馈给开发定位问题 (N192 B7 复现路径). */}
          <Tooltip title={t('btn_copy_diagnosis')}>
            <Button size="small" type="text" icon={<CopyOutlined />} onClick={handleCopyDiagnosis} disabled={!trace} />
          </Tooltip>
        </div>
      }
      open={open}
      onClose={onClose}
      width={640}
      destroyOnClose
    >
      {loading ? (
        <div className="gaf-flex gaf-flex-center" style={{ padding: 40, justifyContent: 'center' }}>
          <Spin />
        </div>
      ) : errorMsg ? (
        // N192 B1: 错误提示归一 — 后端 friendly message 直接展示
        <Alert
          type="warning"
          showIcon
          title={t('executions.node_detail_fetch_failed')}
          description={errorMsg}
          action={
            <Button size="small" onClick={fetchTrace}>
              {t('executions.node_detail_refresh')}
            </Button>
          }
        />
      ) : !trace ? (
        <Empty description={t('executions.node_detail_empty')} />
      ) : (
        <div>
          {/* 基本信息卡片 */}
          <Card size="small" title={t('executions.node_detail_basic_info')} style={{ marginBottom: 12 }}>
            <div className="gaf-flex-col" style={{ gap: 4 }}>
              <div>
                <Text type="secondary">{t('executions.node_detail_node_id')}:</Text>{' '}
                <Text strong>{trace.node_id || '-'}</Text>
              </div>
              <div>
                <Text type="secondary">{t('executions.node_detail_node_type')}:</Text>{' '}
                <Tag color="blue">{trace.node_type || '-'}</Tag>
              </div>
              <div>
                <Text type="secondary">{t('executions.node_detail_step_index')}:</Text> <Text>{trace.step_index}</Text>
              </div>
              <div>
                <Text type="secondary">{t('executions.node_detail_status')}:</Text> {renderStatusTag(trace.success)}
              </div>
              <div>
                <Text type="secondary">{t('executions.node_detail_elapsed')}:</Text>{' '}
                <Text>{(trace.elapsed_ms / 1000).toFixed(2)}s</Text>
                {trace.retry_count > 0 && (
                  <Text type="warning" style={{ marginLeft: 8 }}>
                    ({t('executions.node_detail_retry_count', { count: trace.retry_count })})
                  </Text>
                )}
              </div>
              {trace.coord_system && (
                <div>
                  <Text type="secondary">{t('executions.node_detail_coord_system')}:</Text>{' '}
                  <Tag color="cyan">{trace.coord_system}</Tag>
                </div>
              )}
            </div>
          </Card>

          {/* 失败信息卡片 (只在失败时显示) — N192 B3 错误定位 */}
          {trace.success === false && (trace.error_msg || trace.error_code) && (
            <Card
              size="small"
              title={<span style={{ color: token.colorError }}>{t('executions.node_detail_error_info')}</span>}
              style={{ marginBottom: 12, borderColor: token.colorError }}
            >
              <div className="gaf-flex-col" style={{ gap: 4 }}>
                {trace.error_code && (
                  <div>
                    <Text type="secondary">{t('executions.node_detail_error_code')}:</Text>{' '}
                    {/* Task 4.54 (P1-34, 2026-07-28): error_code i18n 映射.
                        与 StepProgressBar.tsx:161 一致: 按 error.codes.<CODE> 映射多语言文案,
                        i18n 找不到 key 时返回 key 本身, 此时降级展示原始 error_code (N192 B1/B2). */}
                    {(() => {
                      const i18nKey = `error.codes.${trace.error_code}`;
                      const mapped = t(i18nKey);
                      return <Tag color="error">{mapped && mapped !== i18nKey ? mapped : trace.error_code}</Tag>;
                    })()}
                  </div>
                )}
                {trace.error_msg && (
                  <div>
                    <Text type="secondary">{t('executions.node_detail_error_msg')}:</Text>
                    <Paragraph
                      style={{
                        marginTop: 4,
                        marginBottom: 0,
                        padding: 8,
                        background: token.colorBgLayout,
                        borderRadius: token.borderRadius,
                        color: token.colorError,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-all',
                      }}
                    >
                      {trace.error_msg}
                    </Paragraph>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* 识别类节点诊断字段 — 让用户看到 "匹配到了 0.92 但阈值 0.8" */}
          {(trace.confidence !== null || trace.threshold !== null || trace.match_location || trace.roi_physical) && (
            <Card size="small" title={t('executions.node_detail_recognition')} style={{ marginBottom: 12 }}>
              <div className="gaf-flex-col" style={{ gap: 4 }}>
                {trace.confidence !== null && (
                  <div>
                    <Text type="secondary">{t('executions.node_detail_confidence')}:</Text>{' '}
                    <Text strong>{trace.confidence.toFixed(4)}</Text>
                  </div>
                )}
                {trace.threshold !== null && (
                  <div>
                    <Text type="secondary">{t('executions.node_detail_threshold')}:</Text>{' '}
                    <Text strong>{trace.threshold}</Text>
                  </div>
                )}
                {trace.match_location && (
                  <div>
                    <Text type="secondary">{t('executions.node_detail_match_location')}:</Text>{' '}
                    <Text>
                      ({trace.match_location.x}, {trace.match_location.y})
                    </Text>
                  </div>
                )}
                {trace.roi_physical && (
                  <div>
                    <Text type="secondary">{t('executions.node_detail_roi')}:</Text>{' '}
                    <Text>[{trace.roi_physical.join(', ')}]</Text>
                  </div>
                )}
                {trace.screenshot_path && (
                  <div>
                    <Text type="secondary">{t('executions.node_detail_screenshot')}:</Text>{' '}
                    <Text code style={{ fontSize: 11 }}>
                      {trace.screenshot_path}
                    </Text>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* 节点设计语义 — spec 阶段 4.3 */}
          {(trace.comment || trace.rationale) && (
            <Card size="small" title={t('executions.node_detail_design')} style={{ marginBottom: 12 }}>
              <div className="gaf-flex-col" style={{ gap: 4 }}>
                {trace.comment && (
                  <div>
                    <Text type="secondary">{t('executions.node_detail_comment')}:</Text> <Text>{trace.comment}</Text>
                  </div>
                )}
                {trace.rationale && (
                  <div>
                    <Text type="secondary">{t('executions.node_detail_rationale')}:</Text>{' '}
                    <Text type="secondary">{trace.rationale}</Text>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* 节点 input_config — N192 B7 核心字段: 让用户看到 "这个节点当时配的 threshold/ROI" */}
          <Title level={5} style={{ marginTop: 16, marginBottom: 8 }}>
            {t('executions.node_detail_input_config_title')}
          </Title>
          <JsonBlock
            title={t('executions.node_detail_input_config')}
            data={trace.input_config}
            token={token}
            defaultExpanded={false}
          />

          {/* 前驱节点 result_data — N192 A4 P2: 让用户定位 "前驱输出 → 当前输入" */}
          <Title level={5} style={{ marginTop: 16, marginBottom: 8 }}>
            {t('executions.node_detail_previous_result_title')}
          </Title>
          <JsonBlock
            title={
              trace.previous_node_id
                ? t('executions.node_detail_previous_result_with_id', {
                    id: trace.previous_node_id,
                    type: trace.previous_node_type || '?',
                  })
                : t('executions.node_detail_previous_result')
            }
            data={trace.previous_node_result_data}
            token={token}
            defaultExpanded={false}
          />

          {/* 调试信息: structured_log_path — 让用户能反馈给开发定位日志文件 */}
          <Card size="small" type="inner" title={t('executions.node_detail_debug_info')} style={{ marginTop: 16 }}>
            <Text type="secondary" style={{ fontSize: 11, wordBreak: 'break-all' }}>
              {t('executions.node_detail_log_path')}: {trace.structured_log_path || '-'}
            </Text>
          </Card>
        </div>
      )}
    </Drawer>
  );
}

export default NodeDetailDrawer;
