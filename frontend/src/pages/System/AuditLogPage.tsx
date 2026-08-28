/**
 * Audit Log viewer page
 * Read-only log display: user, action, resource type, resource ID,
 * IP address, timestamp, details JSON (Drawer)
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import { Table, Button, Space, Tag, Card, Drawer, Input, Select, Typography, theme } from 'antd';
import { ReloadOutlined, EyeOutlined, SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchAuditLogs } from '@/api/accounts';
import type { AuditLog } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

const { Text } = Typography;

/** Action Tag color mapping */
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

/** Action i18n key mapping */
const ACTION_LABEL_KEYS: Record<string, string> = {
  login: 'auditLog.action_login',
  logout: 'auditLog.action_logout',
  create: 'auditLog.action_create',
  update: 'auditLog.action_update',
  delete: 'auditLog.action_delete',
  execute: 'auditLog.action_execute',
  import: 'auditLog.action_import',
  export: 'auditLog.action_export',
};

/** Resource type i18n key mapping */
const RESOURCE_TYPE_LABEL_KEYS: Record<string, string> = {
  user: 'auditLog.resource_user',
  task: 'auditLog.resource_task',
  device: 'auditLog.resource_device',
  resource_pack: 'auditLog.resource_resource_pack',
  api_key: 'auditLog.resource_api_key',
  feature_flag: 'auditLog.resource_feature_flag',
  game_account: 'auditLog.resource_game_account',
  game_profile: 'auditLog.resource_game_profile',
  // spec34 Phase 4: 30 new resource types (must match AuditResourceType in backend/gaf_core/audit_constants.py)
  agent: 'auditLog.resource_agent',
  agent_token: 'auditLog.resource_agent_token',
  pipeline: 'auditLog.resource_pipeline',
  scheduled_task: 'auditLog.resource_scheduled_task',
  task_chain: 'auditLog.resource_task_chain',
  task_folder: 'auditLog.resource_task_folder',
  custom_task: 'auditLog.resource_custom_task',
  recording: 'auditLog.resource_recording',
  template_version: 'auditLog.resource_template_version',
  template_annotation: 'auditLog.resource_template_annotation',
  tag: 'auditLog.resource_tag',
  plugin: 'auditLog.resource_plugin',
  time_window: 'auditLog.resource_time_window',
  notification: 'auditLog.resource_notification',
  webhook_config: 'auditLog.resource_webhook_config',
  alert_rule: 'auditLog.resource_alert_rule',
  monitor_rule: 'auditLog.resource_monitor_rule',
  agent_session: 'auditLog.resource_agent_session',
  qa_session: 'auditLog.resource_qa_session',
  qa_message: 'auditLog.resource_qa_message',
  crash_report: 'auditLog.resource_crash_report',
  debug_log_archive: 'auditLog.resource_debug_log_archive',
  game_state_rule: 'auditLog.resource_game_state_rule',
  task_execution: 'auditLog.resource_task_execution',
  user_session: 'auditLog.resource_user_session',
  game_account_group: 'auditLog.resource_game_account_group',
  rotation_rule: 'auditLog.resource_rotation_rule',
  llm_config: 'auditLog.resource_llm_config',
  app_settings: 'auditLog.resource_app_settings',
  unattended_strategy: 'auditLog.resource_unattended_strategy',
  device_group: 'auditLog.resource_device_group',
  marketplace: 'auditLog.resource_marketplace',
};

export function AuditLogPage() {
  const { token } = theme.useToken();
  const t = useTranslation();
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [searchText, setSearchText] = useState('');
  const [actionFilter, setActionFilter] = useState<string | undefined>(undefined);

  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  const actionLabel = useMemo(() => {
    const map: Record<string, string> = {};
    Object.entries(ACTION_LABEL_KEYS).forEach(([k, key]) => {
      map[k] = t(key);
    });
    return map;
  }, [t]);

  const resourceTypeLabel = useMemo(() => {
    const map: Record<string, string> = {};
    Object.entries(RESOURCE_TYPE_LABEL_KEYS).forEach(([k, key]) => {
      map[k] = t(key);
    });
    return map;
  }, [t]);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchAuditLogs({
        page,
        page_size: pageSize,
        search: searchText || undefined,
        action: actionFilter || undefined,
        resource_type: searchText || undefined,
      });
      setLogs(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      // Error message handled silently
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchText, actionFilter]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const handleViewDetails = (record: AuditLog) => {
    setSelectedLog(record);
    setDetailOpen(true);
  };

  const columns: ColumnsType<AuditLog> = [
    {
      title: t('auditLog.col_user'),
      dataIndex: 'username',
      key: 'username',
      width: 120,
      render: (username: string | null) => username || t('auditLog.system_user'),
    },
    {
      title: t('auditLog.col_action'),
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (action: string) => {
        const color = ACTION_COLOR_MAP[action] || 'default';
        const label = actionLabel[action] || action;
        return <Tag color={color}>{label}</Tag>;
      },
      filters: Object.keys(ACTION_COLOR_MAP).map((a) => ({
        text: actionLabel[a] || a,
        value: a,
      })),
      onFilter: (value, record) => record.action === value,
    },
    {
      title: t('auditLog.col_resource_type'),
      dataIndex: 'resource_type',
      key: 'resource_type',
      width: 120,
      render: (type: string) => resourceTypeLabel[type] || type,
    },
    {
      title: t('auditLog.col_resource_id'),
      dataIndex: 'resource_id',
      key: 'resource_id',
      width: 140,
      ellipsis: true,
      render: (id: string) => <Text code>{id}</Text>,
    },
    {
      title: t('auditLog.col_ip'),
      dataIndex: 'ip_address',
      key: 'ip_address',
      width: 140,
      render: (ip: string | null) => ip || '-',
    },
    {
      title: t('auditLog.col_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => dayjs(text).locale(getLocale()).format('YYYY-MM-DD HH:mm:ss'),
      sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    },
    {
      title: t('auditLog.col_details'),
      key: 'details',
      width: 80,
      render: (_: unknown, record: AuditLog) => (
        <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleViewDetails(record)}>
          {t('auditLog.btn_view')}
        </Button>
      ),
    },
  ];

  /** Action options for select filter */
  const actionOptions = Object.entries(actionLabel).map(([value, label]) => ({
    value,
    label,
  }));

  return (
    <PageWrapper
      title={t('auditLog.page_title')}
      extra={
        <Space>
          <Select
            allowClear
            placeholder={t('auditLog.filter_action')}
            style={{ width: 140 }}
            options={actionOptions}
            value={actionFilter}
            onChange={(val) => {
              setActionFilter(val);
              setPage(1);
            }}
          />
          <Input.Search
            placeholder={t('auditLog.search_placeholder')}
            allowClear
            style={{ width: 180 }}
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={() => {
              setPage(1);
              loadLogs();
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => loadLogs()}>
            {t('auditLog.btn_refresh')}
          </Button>
        </Space>
      }
    >
      <Card>
        <Table<AuditLog>
          rowKey="id"
          columns={columns}
          dataSource={logs}
          loading={loading}
          scroll={{ x: 1000 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (total) => t('auditLog.total_count', { count: total }),
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>

      <Drawer
        title={t('auditLog.drawer_title')}
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
              <Text strong>{t('auditLog.lbl_user')}</Text>
              <Text>{selectedLog.username || t('auditLog.system_user')}</Text>
            </div>
            <div className="gaf-mb-lg">
              <Text strong>{t('auditLog.lbl_action')}</Text>
              <Tag color={ACTION_COLOR_MAP[selectedLog.action] || 'default'}>
                {actionLabel[selectedLog.action] || selectedLog.action}
              </Tag>
            </div>
            <div className="gaf-mb-lg">
              <Text strong>{t('auditLog.lbl_resource_type')}</Text>
              <Text>{resourceTypeLabel[selectedLog.resource_type] || selectedLog.resource_type}</Text>
            </div>
            <div className="gaf-mb-lg">
              <Text strong>{t('auditLog.lbl_resource_id')}</Text>
              <Text code>{selectedLog.resource_id}</Text>
            </div>
            <div className="gaf-mb-lg">
              <Text strong>{t('auditLog.lbl_ip')}</Text>
              <Text>{selectedLog.ip_address || '-'}</Text>
            </div>
            <div className="gaf-mb-lg">
              <Text strong>{t('auditLog.lbl_created_at')}</Text>
              <Text>{dayjs(selectedLog.created_at).locale(getLocale()).format('YYYY-MM-DD HH:mm:ss')}</Text>
            </div>
            <div>
              <Text strong>{t('auditLog.lbl_details_json')}</Text>
              <pre
                className="gaf-mt-sm gaf-p-md gaf-text-xs gaf-overflow-auto"
                style={{ background: token.colorFillQuaternary, borderRadius: 4, maxHeight: 400 }}
              >
                {JSON.stringify(selectedLog.details, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </Drawer>
    </PageWrapper>
  );
}

export default AuditLogPage;
