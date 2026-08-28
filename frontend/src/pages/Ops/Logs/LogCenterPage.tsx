/**
 * Log Center Page — unified log viewer with 8 specialized tabs (C.5).
 *
 * Tabs:
 *  1. 统一时间线 — UNION query across 6 log models via /api/v2/logs/timeline/
 *  2. 应用日志 — LogEntry records (DatabaseLogHandler persistence layer)
 *  3. 审计日志 — AuditLog (user actions: login/create/update/delete/...)
 *  4. 恢复日志 — RecoveryLog (5-layer recovery mechanism history)
 *  5. 消息帧日志 — MessageFrameLog (agent ↔ backend protocol frames)
 *  6. LLM 调用日志 — LLMUsageLog (token usage + cost per LLM call)
 *  7. 崩溃报告 — CrashReport (component crashes with stack traces)
 *  8. 日志归档 — DebugLogArchive (upload + browse; LLM analysis in /ai/log-analysis)
 *
 * The "应用日志" tab subscribes to /ws/logs/ (LogStreamConsumer) for
 * real-time push of new entries — they are prepended to the table
 * without a manual refresh.
 *
 * Route: /ops/logs
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Drawer,
  Input,
  Select,
  Typography,
  DatePicker,
  Tabs,
  Alert,
  Tooltip,
  theme,
} from 'antd';
import { ReloadOutlined, EyeOutlined, SearchOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchLogEntries, fetchUnifiedTimeline, type UnifiedLogEntry } from '@/api/logs';
import type { LogEntry } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';
import { useLogStream, type LogStreamEntry } from '@/hooks/useLogStream';
import {
  AuditLogTab,
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

type LogCenterTabKey = 'unified' | 'app' | 'audit' | 'recovery' | 'message' | 'llm' | 'crash' | 'archive';

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
            key: 'audit',
            label: t('logCenter.tab_audit_log'),
            children: <AuditLogTab />,
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
// Application Log Tab (LogEntry) — with WebSocket real-time push
// ─────────────────────────────────────────────

function AppLogTab() {
  const t = useTranslation();
  const { token } = theme.useToken();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Filters
  const [levelFilter, setLevelFilter] = useState<string | undefined>(undefined);
  const [sourceFilter, setSourceFilter] = useState('');
  const [timeRange, setTimeRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [searchText, setSearchText] = useState('');
  const [traceIdFilter, setTraceIdFilter] = useState('');

  // Detail drawer
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);

  // Real-time push buffer (prepended entries from /ws/logs/)
  const [realtimeCount, setRealtimeCount] = useState(0);
  const realtimeBuffer = useRef<LogEntry[]>([]);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params: Parameters<typeof fetchLogEntries>[0] = {
        page,
        page_size: pageSize,
      };
      if (levelFilter) params.level = levelFilter;
      if (sourceFilter.trim()) params.source = sourceFilter.trim();
      if (searchText.trim()) params.search = searchText.trim();
      if (traceIdFilter.trim()) params.trace_id = traceIdFilter.trim();
      if (timeRange && timeRange[0]) params.start = timeRange[0].toISOString();
      if (timeRange && timeRange[1]) params.end = timeRange[1].toISOString();

      const res = await fetchLogEntries(params);
      setLogs(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      // Error message handled silently by axios interceptor
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, levelFilter, sourceFilter, timeRange, searchText, traceIdFilter]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  // Subscribe to /ws/logs/ for real-time push. New entries are buffered
  // and surfaced as a "N new entries" banner; clicking it merges them in.
  const handleRealtimeEntry = useCallback((entry: LogStreamEntry) => {
    // LogStreamEntry (无 id) 与 LogEntry (有 id) 字段集不同,
    // 实时推送无 id, 用 type assertion 兼容存入 buffer (merge 时直接展开)
    realtimeBuffer.current = [entry as unknown as LogEntry, ...realtimeBuffer.current].slice(0, MAX_REALTIME_BUFFER);
    setRealtimeCount(realtimeBuffer.current.length);
  }, []);

  const { isConnected } = useLogStream(handleRealtimeEntry);

  const mergeRealtime = () => {
    if (realtimeBuffer.current.length === 0) return;
    setLogs((prev) => [...realtimeBuffer.current, ...prev].slice(0, MAX_REALTIME_BUFFER));
    realtimeBuffer.current = [];
    setRealtimeCount(0);
  };

  const handleViewDetails = (record: LogEntry) => {
    setSelectedLog(record);
    setDetailOpen(true);
  };

  const handleResetPage = () => setPage(1);

  const columns: ColumnsType<LogEntry> = [
    {
      title: t('logCenter.col_timestamp'),
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (text: string) => dayjs(text).locale(getLocale()).format('YYYY-MM-DD HH:mm:ss'),
      sorter: (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      defaultSortOrder: 'descend',
    },
    {
      title: t('logCenter.col_level'),
      dataIndex: 'level',
      key: 'level',
      width: 100,
      render: (level: string) => <Tag color={LEVEL_COLOR_MAP[level] || 'default'}>{level}</Tag>,
      filters: LEVEL_OPTIONS.map((l) => ({ text: l, value: l })),
      onFilter: (value, record) => record.level === value,
    },
    {
      title: t('logCenter.col_source'),
      dataIndex: 'source',
      key: 'source',
      width: 180,
      ellipsis: true,
      render: (source: string) => <Text code>{source}</Text>,
    },
    {
      title: t('logCenter.col_message'),
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      render: (message: string) => <Text>{message}</Text>,
    },
    {
      title: t('logCenter.col_trace_id'),
      dataIndex: 'trace_id',
      key: 'trace_id',
      width: 120,
      ellipsis: true,
      render: (v: string | null) => (v ? <Text code>{v.slice(0, 8)}…</Text> : <Text type="secondary">-</Text>),
    },
    {
      title: t('logCenter.col_actions'),
      key: 'actions',
      width: 80,
      render: (_: unknown, record: LogEntry) => (
        <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleViewDetails(record)}>
          {t('logCenter.btn_view')}
        </Button>
      ),
    },
  ];

  return (
    <div>
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
            loadLogs();
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
        <Input.Search
          placeholder={t('logCenter.search_placeholder')}
          allowClear
          style={{ width: 200 }}
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onSearch={() => {
            handleResetPage();
            loadLogs();
          }}
        />
        <Input
          allowClear
          placeholder={t('logCenter.filter_trace_id_placeholder')}
          style={{ width: 200 }}
          value={traceIdFilter}
          onChange={(e) => setTraceIdFilter(e.target.value)}
          onPressEnter={() => {
            handleResetPage();
            loadLogs();
          }}
        />
        <Button icon={<ReloadOutlined />} onClick={() => loadLogs()}>
          {t('logCenter.btn_refresh')}
        </Button>
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

      <Table<LogEntry>
        rowKey="id"
        columns={columns}
        dataSource={logs}
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

      <Drawer
        title={t('logCenter.drawer_title')}
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setSelectedLog(null);
        }}
        size={560}
        destroyOnHidden
      >
        {selectedLog && (
          <div className="gaf-text-sm">
            <div className="gaf-mb-lg">
              <Text strong>{t('logCenter.lbl_timestamp')}</Text>
              <Text>{dayjs(selectedLog.timestamp).locale(getLocale()).format('YYYY-MM-DD HH:mm:ss')}</Text>
            </div>
            <div className="gaf-mb-lg">
              <Text strong>{t('logCenter.lbl_level')}</Text>
              <Tag color={LEVEL_COLOR_MAP[selectedLog.level] || 'default'}>{selectedLog.level}</Tag>
            </div>
            <div className="gaf-mb-lg">
              <Text strong>{t('logCenter.lbl_source')}</Text>
              <Text code>{selectedLog.source}</Text>
            </div>
            <div className="gaf-mb-lg">
              <Text strong>{t('logCenter.lbl_message')}</Text>
              <Text>{selectedLog.message}</Text>
            </div>
            {selectedLog.task_id !== null && (
              <div className="gaf-mb-lg">
                <Text strong>{t('logCenter.lbl_task_id')}</Text>
                <Text code>{selectedLog.task_id}</Text>
              </div>
            )}
            {selectedLog.agent_id !== null && (
              <div className="gaf-mb-lg">
                <Text strong>{t('logCenter.lbl_agent_id')}</Text>
                <Text code>{selectedLog.agent_id}</Text>
              </div>
            )}
            {selectedLog.device_id !== null && (
              <div className="gaf-mb-lg">
                <Text strong>{t('logCenter.lbl_device_id')}</Text>
                <Text code>{selectedLog.device_id}</Text>
              </div>
            )}
            {selectedLog.trace_id !== null && (
              <div className="gaf-mb-lg">
                <Text strong>{t('logCenter.col_trace_id')}</Text>
                <Text code>{selectedLog.trace_id}</Text>
              </div>
            )}
            <div>
              <Text strong>{t('logCenter.lbl_traceback')}</Text>
              {selectedLog.traceback ? (
                <pre
                  className="gaf-mt-sm gaf-p-md gaf-text-xs gaf-radius-sm gaf-overflow-auto"
                  style={{ background: token.colorFillQuaternary, maxHeight: 400 }}
                >
                  {selectedLog.traceback}
                </pre>
              ) : (
                <Text type="secondary">{t('logCenter.no_traceback')}</Text>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}

export default LogCenterPage;
