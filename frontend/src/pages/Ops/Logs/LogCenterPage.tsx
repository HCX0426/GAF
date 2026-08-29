/**
 * Log Center Page — unified log viewer with 7 specialized tabs (C.5; 审计
 * tab 移除, 收敛到系统页 /system/audit-log — TD-418).
 *
 * Tabs:
 *  1. 统一时间线 — UNION query across 6 log models via /api/v2/logs/timeline/
 *  2. 应用日志 — file-layer logs via /api/v2/logs/files/ (spec 2026-08-29
 *     logging-system-consolidation P2-2: LogEntry 表已停写, 应用日志以文件层为准)
 *  3. 恢复日志 — RecoveryLog (5-layer recovery mechanism history)
 *  4. 消息帧日志 — MessageFrameLog (agent ↔ backend protocol frames)
 *  5. LLM 调用日志 — LLMUsageLog (token usage + cost per LLM call)
 *  6. 崩溃报告 — CrashReport (component crashes with stack traces)
 *  7. 日志归档 — DebugLogArchive (upload + browse; LLM analysis in /ai/log-analysis)
 *
 * The "应用日志" tab subscribes to /ws/logs/ (LogStreamConsumer) for
 * real-time push of new entries — they are prepended to the file log view
 * without a manual refresh.
 *
 * Route: /ops/logs
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Alert,
  Button,
  DatePicker,
  Empty,
  Input,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  theme,
} from 'antd';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchFileLogs, fetchUnifiedTimeline, type UnifiedLogEntry } from '@/api/logs';
import { useTranslation, getLocale } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';
import { useLogStream, type LogStreamEntry } from '@/hooks/useLogStream';
import {
  RecoveryLogTab,
  MessageFrameTab,
  LLMUsageTab,
  CrashReportTab,
  ArchiveLogTab,
} from './SpecialtyLogTabs';

const { Text } = Typography;
const { RangePicker } = DatePicker;

/** Level → Tag color mapping */
const LEVEL_COLOR_MAP: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'blue',
  WARNING: 'orange',
  ERROR: 'red',
  CRITICAL: 'magenta',
};

/** Level options for the multi-select filter */
const LEVEL_OPTIONS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

/** Cap on real-time entries cached client-side before older ones are dropped. */
const MAX_REALTIME_BUFFER = 200;

type LogCenterTabKey = 'unified' | 'app' | 'recovery' | 'message' | 'llm' | 'crash' | 'archive';

export function LogCenterPage() {
  const t = useTranslation();
  const [activeTab, setActiveTab] = useState<LogCenterTabKey>('unified');

  return (
    <PageWrapper title={t('logCenter.page_title')}>
      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as LogCenterTabKey)}
        items={[
          {
            key: 'unified',
            label: (
              <span>
                <ThunderboltOutlined />
                <span style={{ marginLeft: 6 }}>{t('logCenter.tab_unified')}</span>
              </span>
            ),
            children: <UnifiedTimelineTab />,
          },
          {
            key: 'app',
            label: t('logCenter.tab_app_log'),
            children: <AppLogTab />,
          },
          {
            key: 'recovery',
            label: t('logCenter.tab_recovery_log'),
            children: <RecoveryLogTab />,
          },
          {
            key: 'message',
            label: t('logCenter.tab_message_frame'),
            children: <MessageFrameTab />,
          },
          {
            key: 'llm',
            label: t('logCenter.tab_llm_usage'),
            children: <LLMUsageTab />,
          },
          {
            key: 'crash',
            label: t('logCenter.tab_crash_report'),
            children: <CrashReportTab />,
          },
          {
            key: 'archive',
            label: t('logCenter.tab_archive'),
            children: <ArchiveLogTab />,
          },
        ]}
      />
    </PageWrapper>
  );
}

// ─────────────────────────────────────────────
// Unified Timeline Tab (UNION across 6 log models)
// ─────────────────────────────────────────────

function UnifiedTimelineTab() {
  const t = useTranslation();
  const [data, setData] = useState<UnifiedLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [levelFilter, setLevelFilter] = useState<string | undefined>(undefined);
  const [sourceFilter, setSourceFilter] = useState('');
  const [timeRange, setTimeRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Parameters<typeof fetchUnifiedTimeline>[0] = { page, page_size: pageSize };
      if (levelFilter) params.level = levelFilter;
      if (sourceFilter.trim()) params.source = sourceFilter.trim();
      if (timeRange && timeRange[0]) params.start = timeRange[0].toISOString();
      if (timeRange && timeRange[1]) params.end = timeRange[1].toISOString();
      const res = await fetchUnifiedTimeline(params);
      setData(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      // axios interceptor surfaces the error
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, levelFilter, sourceFilter, timeRange]);

  useEffect(() => {
    load();
  }, [load]);

  const handleResetPage = () => setPage(1);

  const columns: ColumnsType<UnifiedLogEntry> = [
    {
      title: t('logCenter.col_occurred_at'),
      dataIndex: 'occurred_at',
      key: 'occurred_at',
      width: 180,
      render: (v: string) => dayjs(v).locale(getLocale()).format('YYYY-MM-DD HH:mm:ss'),
      sorter: (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime(),
      defaultSortOrder: 'descend',
    },
    {
      title: t('logCenter.col_ref_type'),
      dataIndex: 'ref_type',
      key: 'ref_type',
      width: 140,
      render: (v: string) => <Tag color="purple">{v}</Tag>,
    },
    {
      title: t('logCenter.col_log_level'),
      dataIndex: 'log_level',
      key: 'log_level',
      width: 100,
      render: (v: string) => <Tag color={LEVEL_COLOR_MAP[v] || 'default'}>{v}</Tag>,
    },
    {
      title: t('logCenter.col_log_source'),
      dataIndex: 'log_source',
      key: 'log_source',
      width: 200,
      ellipsis: true,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: t('logCenter.col_log_message'),
      dataIndex: 'log_message',
      key: 'log_message',
      ellipsis: true,
      render: (v: string) => <Text>{v}</Text>,
    },
  ];

  return (
    <div>
      <Alert type="info" showIcon title={t('logCenter.tab_unified_hint')} className="gaf-mb-md" />
      <Space wrap className="gaf-mb-md">
        <Select
          allowClear
          placeholder={t('logCenter.filter_level')}
          style={{ width: 140 }}
          options={LEVEL_OPTIONS.map((l) => ({ value: l, label: l }))}
          value={levelFilter}
          onChange={(val) => {
            setLevelFilter(val);
            handleResetPage();
          }}
        />
        <Input
          allowClear
          placeholder={t('logCenter.filter_source_placeholder')}
          style={{ width: 200 }}
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          onPressEnter={() => {
            handleResetPage();
            load();
          }}
        />
        <RangePicker
          showTime
          value={timeRange}
          onChange={(range) => {
            setTimeRange(range as [Dayjs | null, Dayjs | null] | null);
            handleResetPage();
          }}
        />
        <Button icon={<ReloadOutlined />} onClick={() => load()}>
          {t('logCenter.btn_refresh')}
        </Button>
      </Space>
      <Table<UnifiedLogEntry>
        rowKey={(r) => `${r.ref_type}-${r.ref_id}`}
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 900 }}
        size="small"
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (count) => t('logCenter.total_count', { count }),
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// Application Log Tab (file-layer) — 统一文件日志检索 + WebSocket 实时推送
// spec 2026-08-29-logging-system-consolidation P2-2: LogEntry 表已停写,
// 应用日志以文件层为准 (服务终端捕获 + 原生日志), 通过 /logs/files/ 查询.
// ─────────────────────────────────────────────

const SERVICE_LOG_OPTIONS = [
  { value: 'backend', label: 'backend' },
  { value: 'agent', label: 'agent' },
  { value: 'daemon', label: 'daemon' },
  { value: 'frontend', label: 'frontend' },
  { value: 'redis', label: 'redis' },
];

/** 文件日志行报错高亮 (与 backend/scripts 语义一致). */
const FILE_LINE_ERROR_RE =
  /\b(ERROR|CRITICAL|FATAL)\b|Traceback \(most recent call last\)|(?:Exception|Error)[:(]/;

function AppLogTab() {
  const t = useTranslation();
  const { token } = theme.useToken();
  const [lines, setLines] = useState<string[]>([]);
  const [service, setService] = useState('backend');
  const [filter, setFilter] = useState<'all' | 'error'>('all');
  const [logPath, setLogPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Real-time push buffer (prepended entries from /ws/logs/)
  const [realtimeCount, setRealtimeCount] = useState(0);
  const realtimeBuffer = useRef<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchFileLogs({ service, lines: 400, filter });
      setLines(res.lines ?? []);
      setLogPath(res.path);
    } catch {
      // axios interceptor surfaces the error
    } finally {
      setLoading(false);
    }
  }, [service, filter]);

  useEffect(() => {
    load();
  }, [load]);

  // Subscribe to /ws/logs/ for real-time push — FileLogHandler broadcasts
  // each emitted line; buffer prepends + banner keeps the file view lively.
  const handleRealtimeEntry = useCallback((entry: LogStreamEntry) => {
    const text = entry.message || JSON.stringify(entry);
    realtimeBuffer.current = [text, ...realtimeBuffer.current].slice(0, MAX_REALTIME_BUFFER);
    setRealtimeCount(realtimeBuffer.current.length);
  }, []);

  const { isConnected } = useLogStream(handleRealtimeEntry);

  const mergeRealtime = () => {
    if (realtimeBuffer.current.length === 0) return;
    setLines((prev) => [...realtimeBuffer.current, ...prev].slice(0, MAX_REALTIME_BUFFER));
    realtimeBuffer.current = [];
    setRealtimeCount(0);
  };

  return (
    <div>
      <Alert
        type="info"
        showIcon
        title={t('logCenter.tab_app_hint')}
        className="gaf-mb-md"
      />
      <Space wrap className="gaf-mb-md">
        <Tooltip title={isConnected ? t('logCenter.ws_connected') : t('logCenter.ws_disconnected')}>
          <Tag color={isConnected ? 'green' : 'default'} style={{ margin: 0 }}>
            <ThunderboltOutlined />
            <span className="gaf-ml-xs">
              {isConnected ? t('logCenter.ws_connected') : t('logCenter.ws_disconnected')}
            </span>
          </Tag>
        </Tooltip>
        <Select
          value={service}
          style={{ width: 140 }}
          options={SERVICE_LOG_OPTIONS}
          onChange={(val) => {
            setService(val);
            setRealtimeCount(0);
            realtimeBuffer.current = [];
          }}
        />
        <Select
          value={filter}
          style={{ width: 130 }}
          options={[
            { value: 'all', label: t('logCenter.filter_all') },
            { value: 'error', label: t('logCenter.filter_error') },
          ]}
          onChange={(val) => setFilter(val as 'all' | 'error')}
        />
        <Button icon={<ReloadOutlined />} onClick={() => load()}>
          {t('logCenter.btn_refresh')}
        </Button>
        {logPath && <Text type="secondary" style={{ fontSize: 12 }}>{logPath}</Text>}
      </Space>

      {realtimeCount > 0 && (
        <Alert
          type="success"
          showIcon
          banner
          title={`${realtimeCount} new real-time entries`}
          action={
            <Button size="small" type="link" onClick={mergeRealtime}>
              Show
            </Button>
          }
          className="gaf-mb-sm"
        />
      )}

      {loading ? (
        <Spin />
      ) : lines.length === 0 ? (
        <Empty description={t('logCenter.no_file_logs')} />
      ) : (
        <div
          style={{
            background: token.colorBgLayout,
            borderRadius: 8,
            padding: 12,
            maxHeight: 560,
            overflow: 'auto',
            fontFamily: "'Consolas', 'Courier New', monospace",
            fontSize: 12,
            lineHeight: 1.6,
          }}
        >
          {lines.map((line, idx) => (
            <div
              key={idx}
              style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                color: FILE_LINE_ERROR_RE.test(line) ? token.colorError : token.colorText,
              }}
            >
              {line || ' '}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default LogCenterPage;
