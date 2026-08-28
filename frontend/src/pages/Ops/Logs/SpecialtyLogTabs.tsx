/**
 * Specialty log tabs for LogCenterPage (C.5).
 *
 * Each tab is a minimal read-only table for one specialized log model.
 * The Archive tab also supports upload (log archive management).
 * LLM analysis of archives is handled by /ai/log-analysis (LogAnalysisPanel).
 */
import { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Space, Button, Typography, Input, Upload, App, Alert, Select, theme } from 'antd';
import type { UploadProps } from 'antd';
import { ReloadOutlined, InboxOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchAuditLogs } from '@/api/accounts';
import { fetchRecoveryLogs, type RecoveryLogEntry } from '@/api/scheduler';
import {
  fetchMessageFrameLogs,
  fetchLLMUsageLogs,
  fetchCrashReports,
  type MessageFrameLogEntry,
  type LLMUsageLogEntry,
  type CrashReportEntry,
} from '@/api/logs';
import { fetchDebugLogs, uploadDebugLog, fetchAnalysisResults } from '@/api/debug';
import { useTranslation, getLocale } from '@/i18n';
import type { AuditLog, DebugLogArchive, LLMAnalysisResult, AnalysisStatus } from '@/types/models';

const { Text } = Typography;

/** Shared formatter for ISO timestamps. */
function formatDateTime(val: string | null | undefined): string {
  if (!val) return '-';
  return dayjs(val).locale(getLocale()).format('YYYY-MM-DD HH:mm:ss');
}

// ─────────────────────────────────────────────
// AuditLog Tab
// ─────────────────────────────────────────────

const ACTION_COLOR_MAP: Record<string, string> = {
  login: 'green',
  logout: 'blue',
  create: 'cyan',
  update: 'orange',
  delete: 'red',
  execute: 'purple',
  import: 'geekblue',
  export: 'volcano',
};

export function AuditLogTab() {
  const t = useTranslation();
  const [data, setData] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page: 1, page_size: 50 };
      if (search.trim()) params.search = search.trim();
      const res = await fetchAuditLogs(params);
      // fetchAuditLogs returns untyped payload — coerce to AuditLog[]
      const rows = (res?.results ?? res ?? []) as AuditLog[];
      setData(rows);
    } catch {
      // axios interceptor surfaces the error
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnsType<AuditLog> = [
    {
      title: t('logCenter.col_occurred_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: t('logCenter.col_user'),
      dataIndex: 'username',
      key: 'username',
      width: 120,
      render: (v: string | null) => <Text>{v ?? '-'}</Text>,
    },
    {
      title: t('logCenter.col_action'),
      dataIndex: 'action',
      key: 'action',
      width: 110,
      render: (v: string) => <Tag color={ACTION_COLOR_MAP[v] || 'default'}>{v}</Tag>,
    },
    {
      title: t('logCenter.col_resource'),
      key: 'resource',
      width: 200,
      render: (_: unknown, r: AuditLog) => (
        <Text code>
          {r.resource_type}/{r.resource_id}
        </Text>
      ),
    },
    {
      title: t('logCenter.col_log_message'),
      dataIndex: 'details',
      key: 'details',
      ellipsis: true,
      render: (d: Record<string, unknown>) => <Text type="secondary">{JSON.stringify(d)}</Text>,
    },
  ];

  return (
    <div>
      <Space className="gaf-mb-md">
        <Input.Search
          allowClear
          placeholder={t('logCenter.search_placeholder')}
          style={{ width: 240 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onSearch={() => load()}
        />
        <Button icon={<ReloadOutlined />} onClick={() => load()}>
          {t('logCenter.btn_refresh')}
        </Button>
      </Space>
      <Table<AuditLog>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 800 }}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// RecoveryLog Tab
// ─────────────────────────────────────────────

export function RecoveryLogTab() {
  const t = useTranslation();
  const [data, setData] = useState<RecoveryLogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchRecoveryLogs();
      setData(res ?? []);
    } catch {
      // axios interceptor surfaces the error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnsType<RecoveryLogEntry> = [
    {
      title: t('logCenter.col_occurred_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: t('logCenter.col_recovery_level'),
      dataIndex: 'recovery_level_display',
      key: 'recovery_level_display',
      width: 110,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: t('logCenter.col_trigger_event'),
      dataIndex: 'trigger_event',
      key: 'trigger_event',
      width: 180,
      ellipsis: true,
    },
    {
      title: t('logCenter.col_action_taken'),
      dataIndex: 'action_taken',
      key: 'action_taken',
      width: 180,
      ellipsis: true,
    },
    {
      title: t('logCenter.col_success'),
      dataIndex: 'success',
      key: 'success',
      width: 90,
      render: (v: boolean) => <Tag color={v ? 'green' : 'red'}>{v ? '✓' : '✗'}</Tag>,
    },
  ];

  return (
    <div>
      <Space className="gaf-mb-md">
        <Button icon={<ReloadOutlined />} onClick={() => load()}>
          {t('logCenter.btn_refresh')}
        </Button>
      </Space>
      <Table<RecoveryLogEntry>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 800 }}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// MessageFrameLog Tab
// ─────────────────────────────────────────────

export function MessageFrameTab() {
  const t = useTranslation();
  const [data, setData] = useState<MessageFrameLogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchMessageFrameLogs({ page: 1, page_size: 50 });
      setData(res?.results ?? []);
    } catch {
      // axios interceptor surfaces the error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnsType<MessageFrameLogEntry> = [
    {
      title: t('logCenter.col_occurred_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: t('logCenter.col_direction'),
      dataIndex: 'direction',
      key: 'direction',
      width: 100,
      render: (v: string) => <Tag color={v === 'inbound' ? 'blue' : 'green'}>{v}</Tag>,
    },
    {
      title: t('logCenter.col_message_type'),
      dataIndex: 'message_type',
      key: 'message_type',
      width: 160,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: t('logCenter.col_trace_id'),
      dataIndex: 'trace_id',
      key: 'trace_id',
      width: 220,
      ellipsis: true,
      render: (v: string) => (
        <Text type="secondary" copyable>
          {v}
        </Text>
      ),
    },
  ];

  return (
    <div>
      <Space className="gaf-mb-md">
        <Button icon={<ReloadOutlined />} onClick={() => load()}>
          {t('logCenter.btn_refresh')}
        </Button>
      </Space>
      <Table<MessageFrameLogEntry>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 800 }}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// LLMUsageLog Tab
// ─────────────────────────────────────────────

export function LLMUsageTab() {
  const t = useTranslation();
  const [data, setData] = useState<LLMUsageLogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchLLMUsageLogs({ page: 1, page_size: 50 });
      setData(res?.results ?? []);
    } catch {
      // axios interceptor surfaces the error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnsType<LLMUsageLogEntry> = [
    {
      title: t('logCenter.col_occurred_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: t('logCenter.col_model_name'),
      dataIndex: 'model_name',
      key: 'model_name',
      width: 160,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: t('logCenter.col_call_type'),
      dataIndex: 'call_type',
      key: 'call_type',
      width: 120,
      render: (v: string) => <Tag color="purple">{v || '-'}</Tag>,
    },
    {
      title: t('logCenter.col_tokens'),
      key: 'tokens',
      width: 140,
      render: (_: unknown, r: LLMUsageLogEntry) => (
        <Text>
          {r.input_tokens}/{r.output_tokens}
        </Text>
      ),
    },
    {
      title: t('logCenter.col_cost'),
      dataIndex: 'cost_estimate',
      key: 'cost_estimate',
      width: 110,
      render: (v: string) => <Text type="secondary">{v}</Text>,
    },
    {
      title: t('logCenter.col_route'),
      dataIndex: 'route',
      key: 'route',
      width: 110,
      render: (v: string) => (v ? <Tag color="cyan">{v}</Tag> : <Text type="secondary">-</Text>),
    },
  ];

  return (
    <div>
      <Space className="gaf-mb-md">
        <Button icon={<ReloadOutlined />} onClick={() => load()}>
          {t('logCenter.btn_refresh')}
        </Button>
      </Space>
      <Table<LLMUsageLogEntry>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 900 }}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// CrashReport Tab
// ─────────────────────────────────────────────

export function CrashReportTab() {
  const t = useTranslation();
  const [data, setData] = useState<CrashReportEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchCrashReports({ page: 1, page_size: 50 });
      setData(res?.results ?? []);
    } catch {
      // axios interceptor surfaces the error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const columns: ColumnsType<CrashReportEntry> = [
    {
      title: t('logCenter.col_occurred_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: t('logCenter.col_component'),
      dataIndex: 'component',
      key: 'component',
      width: 180,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: t('logCenter.col_error_type'),
      dataIndex: 'error_type',
      key: 'error_type',
      width: 200,
      ellipsis: true,
      render: (v: string) => <Tag color="red">{v}</Tag>,
    },
    {
      title: t('logCenter.col_resolved'),
      dataIndex: 'resolved',
      key: 'resolved',
      width: 90,
      render: (v: boolean) => <Tag color={v ? 'green' : 'orange'}>{v ? '✓' : '✗'}</Tag>,
    },
  ];

  return (
    <div>
      <Space className="gaf-mb-md">
        <Button icon={<ReloadOutlined />} onClick={() => load()}>
          {t('logCenter.btn_refresh')}
        </Button>
      </Space>
      <Table<CrashReportEntry>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 800 }}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────
// Archive Log Tab (DebugLogArchive) — upload + list + read-only results
// LLM analysis trigger lives in /ai/log-analysis (LogAnalysisPanel)
// ─────────────────────────────────────────────

const ARCHIVE_STATUS_COLOR: Record<AnalysisStatus, string> = {
  pending: 'default',
  analyzing: 'processing',
  completed: 'success',
  failed: 'error',
};

const { Dragger } = Upload;

export function ArchiveLogTab() {
  const t = useTranslation();
  const { message: msg } = App.useApp();
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const [data, setData] = useState<DebugLogArchive[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([]);
  const [analysisResults, setAnalysisResults] = useState<Record<string, LLMAnalysisResult[]>>({});

  const ARCHIVE_STATUS_LABEL: Record<AnalysisStatus, string> = {
    pending: t('logCenter.status_pending'),
    analyzing: t('logCenter.status_analyzing'),
    completed: t('logCenter.status_completed'),
    failed: t('logCenter.status_failed'),
  };

  const STATUS_OPTIONS = [
    { value: '', label: t('logCenter.filter_all_status') },
    { value: 'pending', label: t('logCenter.status_pending') },
    { value: 'analyzing', label: t('logCenter.status_analyzing') },
    { value: 'completed', label: t('logCenter.status_completed') },
    { value: 'failed', label: t('logCenter.status_failed') },
  ];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: 20 };
      if (statusFilter) params.analysis_status = statusFilter;
      const res = await fetchDebugLogs(params as Parameters<typeof fetchDebugLogs>[0]);
      setData(res.results || []);
      setTotal(res.count);
    } catch {
      // axios interceptor surfaces the error
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: false,
    showUploadList: false,
    customRequest: async ({ file, onSuccess, onError }) => {
      try {
        await uploadDebugLog(file as File);
        msg.success(t('logCenter.msg_upload_success'));
        onSuccess?.(null);
        load();
      } catch {
        msg.error(t('logCenter.msg_upload_failed'));
        onError?.(new Error(t('logCenter.msg_upload_failed')));
      }
    },
  };

  const handleExpand = async (expanded: boolean, record: DebugLogArchive) => {
    if (expanded) {
      setExpandedRowKeys([...expandedRowKeys, record.id]);
      try {
        const results = await fetchAnalysisResults(record.id);
        setAnalysisResults((prev) => ({ ...prev, [record.id]: results }));
      } catch {
        setAnalysisResults((prev) => ({ ...prev, [record.id]: [] }));
      }
    } else {
      setExpandedRowKeys(expandedRowKeys.filter((k) => k !== record.id));
    }
  };

  const renderAnalysisResults = (archiveId: string) => {
    const results = analysisResults[archiveId];
    if (!results || results.length === 0) {
      return <span style={{ color: token.colorTextTertiary }}>{t('logCenter.no_results')}</span>;
    }
    return (
      <div className="gaf-flex-col gaf-gap-sm">
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
              className="gaf-p-md gaf-radius-md"
              style={{ border: `1px solid ${token.colorBorderSecondary}` }}
            >
              <Space className="gaf-mb-xs">
                <Tag color={tagColor}>{r.review_status}</Tag>
                {r.model_name && <span style={{ color: token.colorTextTertiary }}>{r.model_name}</span>}
                {r.confidence != null && (
                  <span style={{ color: token.colorTextTertiary }}>
                    {t('logCenter.confidence_label', { value: (r.confidence * 100).toFixed(1) })}
                  </span>
                )}
              </Space>
              {resultText && (
                <div
                  className="gaf-mt-sm gaf-p-md gaf-radius-md gaf-whitespace-pre-wrap gaf-overflow-auto gaf-text-13 gaf-font-mono"
                  style={{
                    background: token.colorBgLayout,
                    maxHeight: 300,
                  }}
                >
                  {resultText}
                </div>
              )}
              {suggestionsText && (
                <div className="gaf-mt-sm gaf-text-xs" style={{ color: token.colorTextSecondary }}>
                  <strong>{t('logCenter.suggestions_label')}</strong>
                  {suggestionsText}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const columns: ColumnsType<DebugLogArchive> = [
    {
      title: t('logCenter.col_filename'),
      dataIndex: 'zip_file_path',
      key: 'zip_file_path',
      ellipsis: true,
      render: (path: string) => {
        if (!path) return '-';
        const sep = path.includes('\\') ? '\\' : '/';
        const parts = path.split(sep);
        return parts[parts.length - 1] || path;
      },
    },
    {
      title: t('logCenter.col_uploaded_at'),
      dataIndex: 'uploaded_at',
      key: 'uploaded_at',
      width: 180,
      render: (val: string) => formatDateTime(val),
    },
    {
      title: t('logCenter.col_analysis_status'),
      dataIndex: 'analysis_status',
      key: 'analysis_status',
      width: 120,
      render: (status: AnalysisStatus) => (
        <Tag color={ARCHIVE_STATUS_COLOR[status] || 'default'}>{ARCHIVE_STATUS_LABEL[status] || status}</Tag>
      ),
    },
    {
      title: t('logCenter.col_actions'),
      key: 'action',
      width: 120,
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => handleExpand(!expandedRowKeys.includes(record.id), record)}>
          {expandedRowKeys.includes(record.id) ? t('logCenter.btn_collapse') : t('logCenter.btn_detail')}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Alert
        type="info"
        showIcon
        title={t('logCenter.archive_analysis_hint')}
        action={
          <Button size="small" type="link" onClick={() => navigate('/ai/log-analysis')}>
            {t('logCenter.btn_go_analysis')}
          </Button>
        }
        className="gaf-mb-md"
      />
      <Dragger {...uploadProps} className="gaf-mb-lg">
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">{t('logCenter.upload_text')}</p>
        <p className="ant-upload-hint">{t('logCenter.upload_hint')}</p>
      </Dragger>

      <Space className="gaf-mb-md">
        <Select
          allowClear
          placeholder={t('logCenter.filter_analysis_status')}
          style={{ width: 160 }}
          options={STATUS_OPTIONS}
          value={statusFilter || undefined}
          onChange={(val) => {
            setStatusFilter(val || undefined);
            setPage(1);
          }}
        />
        <Button icon={<ReloadOutlined />} onClick={() => load()}>
          {t('logCenter.btn_refresh')}
        </Button>
      </Space>

      <Table<DebugLogArchive>
        rowKey="id"
        columns={columns}
        dataSource={data}
        loading={loading}
        scroll={{ x: 800 }}
        size="small"
        expandable={{
          expandedRowKeys,
          onExpand: handleExpand,
          expandedRowRender: (record) => (
            <div>
              <h4 className="gaf-mb-sm">{t('logCenter.analysis_results_title')}</h4>
              {renderAnalysisResults(record.id)}
            </div>
          ),
        }}
        pagination={{
          total,
          current: page,
          pageSize: 20,
          showTotal: (count) => t('logCenter.total_count', { count }),
          onChange: (p) => setPage(p),
        }}
      />
    </div>
  );
}
