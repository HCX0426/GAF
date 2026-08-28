/**
 * Monitoring & alert page — Phase 3.2 enhanced with alert silence timer (P-019)
 * Rule management (CRUD + quick toggle) + event stream + acknowledgment
 * + alert trends + device health + global silence bar + auto-refresh polling (P-023)
 * + alert rules UI (P-021)
 * + P-024 severity colors (P0/P1/P2/P3) + escalate indicators + acknowledge action
 */
import { useEffect, useState, useRef, useCallback } from 'react';
import {
  Tabs,
  Table,
  Tag,
  Button,
  Space,
  Switch,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  App,
  Popconfirm,
  Tooltip,
  Alert,
  Badge,
  TimePicker,
  theme as antTheme,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  EditOutlined,
  CheckCircleOutlined,
  BellOutlined,
  CloseCircleOutlined,
  MedicineBoxOutlined,
  ThunderboltOutlined,
  RiseOutlined,
  UserOutlined,
} from '@ant-design/icons';
import {
  fetchMonitorRules,
  createMonitorRule,
  updateMonitorRule,
  deleteMonitorRule,
  fetchMonitorEvents,
  acknowledgeEvent,
  diagnose,
  autoFix,
} from '@/api/monitors';
import { fetchAlertRules, createAlertRule, updateAlertRule, deleteAlertRule } from '@/api/monitors';
import { fetchResourcePacks } from '@/api/resources';
import type { MonitorRule, MonitorEvent, MonitorEventSeverity, ResourcePack, AlertRule } from '@/types/models';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useTranslation, getLocale } from '@/i18n';
import AlertHistoryChart from './AlertHistoryChart';
import DeviceHealthGrid from './DeviceHealthGrid';
import RecoveryLogTab from './RecoveryLogTab';
import PageWrapper from '@/components/Common/PageWrapper';

const { TextArea } = Input;

/** Severity → antd Tag color mapping (P-024 4-level: P0 red / P1 orange / P2 yellow / P3 blue ) */
const SEVERITY_COLOR_MAP: Record<MonitorEventSeverity, string> = {
  P0: 'red',
  P1: 'orange',
  P2: 'gold',
  P3: 'blue',
};

/** Format ISO datetime to local string using the current locale */
function formatDateTime(val: string | null | undefined): string {
  if (!val) return '-';
  return new Intl.DateTimeFormat(getLocale(), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(val));
}

/** Rule type values (labels are i18n-ized at render time) */
const RULE_TYPE_VALUES = ['frequency', 'threshold', 'pattern'] as const;

/** Notify method values (labels are i18n-ized at render time) */
const NOTIFY_METHOD_VALUES = ['desktop', 'sound', 'webhook', 'email'] as const;

/** Silence duration options (minutes) — values only, labels i18n-ized at render */
const SILENCE_VALUES = [5, 15, 30, 60] as const;

/** Auto-refresh interval options (seconds) — values only, labels i18n-ized at render */
const REFRESH_VALUES = [0, 5, 15, 30, 60] as const;

export function MonitorsPage() {
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const [activeTab, setActiveTab] = useState('rules');

  const silenceUntilRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [, forceUpdate] = useState(0);

  const startSilence = useCallback((minutes: number) => {
    silenceUntilRef.current = Date.now() + minutes * 60 * 1000;
    if (timerRef.current) clearInterval(timerRef.current);
    forceUpdate((n) => n + 1);
    timerRef.current = setInterval(() => {
      if (silenceUntilRef.current && Date.now() >= silenceUntilRef.current) {
        silenceUntilRef.current = null;
        if (timerRef.current) clearInterval(timerRef.current);
        timerRef.current = null;
        forceUpdate((n) => n + 1);
      } else {
        forceUpdate((n) => n + 1);
      }
    }, 1000);
  }, []);

  const cancelSilence = useCallback(() => {
    silenceUntilRef.current = null;
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    forceUpdate((n) => n + 1);
  }, []);

  useEffect(
    () => () => {
      if (timerRef.current) clearInterval(timerRef.current);
    },
    [],
  );

  const getRemainingText = (): string => {
    const until = silenceUntilRef.current;
    if (!until) return '';
    const remaining = Math.max(0, Math.floor((until - Date.now()) / 1000));
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const isSilent = silenceUntilRef.current !== null && Date.now() < silenceUntilRef.current;

  const [refreshInterval, setRefreshInterval] = useState(0);
  const refreshKeyRef = useRef(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const triggerRefresh = useCallback(() => {
    refreshKeyRef.current += 1;
    forceUpdate((n) => n + 1);
  }, []);

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (refreshInterval > 0) {
      pollRef.current = setInterval(() => triggerRefresh(), refreshInterval * 1000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [refreshInterval, triggerRefresh]);

  const silenceOptions = SILENCE_VALUES.map((v) => {
    if (v === 5) return { label: t('monitors.duration_5min'), value: v };
    if (v === 15) return { label: t('monitors.duration_15min'), value: v };
    if (v === 30) return { label: t('monitors.duration_30min'), value: v };
    return { label: t('monitors.duration_1hour'), value: v };
  });

  const refreshOptions = REFRESH_VALUES.map((v) => {
    if (v === 0) return { label: t('monitors.refresh_manual'), value: v };
    return { label: `${v}s`, value: v };
  });

  return (
    <PageWrapper
      title={t('monitors.page_title')}
      extra={
        <>
          {isSilent ? (
            <Alert
              type="warning"
              icon={<BellOutlined />}
              showIcon
              closable
              onClose={cancelSilence}
              title={
                <span>
                  {t('monitors.silence_active')} <Badge status="processing" text={<b>{getRemainingText()}</b>} />
                  <Button
                    type="link"
                    size="small"
                    icon={<CloseCircleOutlined />}
                    onClick={cancelSilence}
                    className="gaf-ml-sm"
                  >
                    {t('monitors.cancel_silence')}
                  </Button>
                </span>
              }
              className="gaf-flex-1"
            />
          ) : (
            <Space>
              <span style={{ color: token.colorTextSecondary }}>{t('monitors.global_silence')}</span>
              <Select
                placeholder={t('monitors.select_duration')}
                options={silenceOptions}
                onChange={(val) => startSilence(val)}
                style={{ width: 110 }}
                size="small"
              />
            </Space>
          )}
          <Space>
            <span style={{ color: token.colorTextSecondary }}>{t('monitors.auto_refresh')}</span>
            <Select
              options={refreshOptions}
              value={refreshInterval}
              onChange={setRefreshInterval}
              style={{ width: 90 }}
              size="small"
            />
            {refreshInterval > 0 && (
              <Button type="link" size="small" icon={<ReloadOutlined />} onClick={triggerRefresh}>
                {t('monitors.refresh_now')}
              </Button>
            )}
          </Space>
        </>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: 'rules', label: t('monitors.tab_rules'), children: <RulesTab refreshKey={refreshKeyRef.current} /> },
          { key: 'alert-rules', label: t('monitors.tab_alert_rules'), children: <AlertRulesTab /> },
          {
            key: 'events',
            label: t('monitors.tab_events'),
            children: <EventsTab isSilenced={isSilent} refreshKey={refreshKeyRef.current} />,
          },
          {
            key: 'recovery',
            label: t('monitors.tab_recovery'),
            children: <RecoveryLogTab refreshKey={refreshKeyRef.current} />,
          },
          { key: 'history', label: t('monitors.tab_history'), children: <AlertHistoryChart /> },
          { key: 'health', label: t('monitors.tab_health'), children: <DeviceHealthGrid /> },
          { key: 'diagnose', label: t('monitors.tab_diagnose'), children: <DiagnoseTab /> },
        ]}
      />
    </PageWrapper>
  );
}

interface RulesTabProps {
  refreshKey: number;
}

function RulesTab({ refreshKey }: RulesTabProps) {
  const t = useTranslation();
  const { message: msg } = App.useApp();
  const [rules, setRules] = useState<MonitorRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<MonitorRule | null>(null);
  const [form] = Form.useForm();
  const [resourcePacks, setResourcePacks] = useState<ResourcePack[]>([]);

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchMonitorRules({ page: 1, page_size: 100 });
      setRules(res.results || []);
    } catch {
      msg.error(t('monitors.msg_load_rules_failed'));
    } finally {
      setLoading(false);
    }
  }, [msg, t]);

  useEffect(() => {
    loadRules();
  }, [loadRules]);

  useEffect(() => {
    if (refreshKey > 0) loadRules();
  }, [refreshKey, loadRules]);

  useEffect(() => {
    if (modalOpen) {
      // spec35 #12: surface fetch failure instead of swallowing silently.
      fetchResourcePacks({ page: 1, page_size: 100 })
        .then((res) => setResourcePacks(res.results || []))
        .catch((err) => {
          msg.error(t('monitors.load_resource_packs_failed'));
          console.warn('[Monitors] fetchResourcePacks failed:', err);
        });
    }
  }, [modalOpen]);

  const handleCreate = async (values: Partial<MonitorRule>) => {
    try {
      if (editingRule) {
        await updateMonitorRule(editingRule.id, values);
        msg.success(t('monitors.msg_rule_updated'));
      } else {
        await createMonitorRule(values);
        msg.success(t('monitors.msg_rule_created'));
      }
      setModalOpen(false);
      setEditingRule(null);
      form.resetFields();
      loadRules();
    } catch {
      msg.error(t('monitors.msg_operation_failed'));
    }
  };

  const handleEdit = (record: MonitorRule) => {
    setEditingRule(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleDelete = async (ruleId: number) => {
    try {
      await deleteMonitorRule(ruleId);
      msg.success(t('monitors.msg_deleted'));
      loadRules();
    } catch {
      msg.error(t('monitors.msg_delete_failed'));
    }
  };

  const handleToggleActive = async (ruleId: number, isEnabled: boolean) => {
    try {
      await updateMonitorRule(ruleId, { is_enabled: isEnabled });
      setRules((prev) => prev.map((r) => (r.id === ruleId ? { ...r, is_enabled: isEnabled } : r)));
      msg.success(isEnabled ? t('monitors.msg_enabled') : t('monitors.msg_disabled'));
    } catch {
      msg.error(t('monitors.msg_operation_failed'));
    }
  };

  const columns: ColumnsType<MonitorRule> = [
    { title: t('monitors.col_name'), dataIndex: 'name', key: 'name', width: 160, ellipsis: true },
    {
      title: t('monitors.col_rule_definition'),
      dataIndex: 'rule_definition',
      key: 'rule_definition',
      width: 200,
      ellipsis: true,
    },
    {
      title: t('monitors.col_resource_pack'),
      dataIndex: 'resource_pack',
      key: 'resource_pack',
      width: 100,
      render: (val: number | null) => val ?? '-',
    },
    {
      title: t('monitors.col_enabled'),
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 80,
      render: (isEnabled: boolean, record: MonitorRule) => (
        <Switch checked={isEnabled} size="small" onChange={(checked) => handleToggleActive(record.id, checked)} />
      ),
    },
    {
      title: t('monitors.col_action'),
      key: 'action',
      width: 120,
      render: (_, record) => (
        <div className="gaf-flex-center gaf-gap-xs">
          <Tooltip key="edit" title={t('monitors.action_edit')}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              aria-label={t('monitors.action_edit_rule')}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Popconfirm key="delete" title={t('monitors.confirm_delete')} onConfirm={() => handleDelete(record.id)}>
            <Button type="link" danger size="small">
              {t('monitors.action_delete')}
            </Button>
          </Popconfirm>
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="gaf-mb-lg">
        <Space>
          <Button
            type="primary"
            icon={
              <span aria-hidden="true">
                <PlusOutlined />
              </span>
            }
            onClick={() => {
              setEditingRule(null);
              form.resetFields();
              setModalOpen(true);
            }}
          >
            {t('monitors.btn_new_rule')}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadRules}>
            {t('monitors.btn_refresh')}
          </Button>
        </Space>
      </div>
      <Table columns={columns} dataSource={rules || []} rowKey="id" loading={loading} size="small" />
      <Modal
        title={editingRule ? t('monitors.title_edit_rule') : t('monitors.title_new_rule')}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditingRule(null);
        }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Form.Item name="name" label={t('monitors.form_rule_name')} rules={[{ required: true }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="resource_pack" label={t('monitors.form_resource_pack')}>
            <Select
              options={resourcePacks.map((rp) => ({
                value: rp.id,
                label: rp.name || t('monitors.resource_pack_id', { id: rp.id }),
              }))}
              placeholder={t('monitors.placeholder_select_resource_pack')}
              allowClear
              showSearch
              filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
            />
          </Form.Item>
          <Form.Item name="rule_definition" label={t('monitors.form_rule_definition')} rules={[{ required: true }]}>
            <TextArea rows={3} placeholder={t('monitors.placeholder_json_rule')} autoComplete="off" />
          </Form.Item>
          <Form.Item name="is_enabled" label={t('monitors.form_enabled')} valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

/** Alert Rules Tab (P-021) — connects to existing backend AlertRule model */
function AlertRulesTab() {
  const t = useTranslation();
  const { message: msg } = App.useApp();
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);
  const [form] = Form.useForm();

  const ruleTypeOptions = RULE_TYPE_VALUES.map((v) => ({
    value: v,
    label:
      v === 'frequency'
        ? t('monitors.rule_type_frequency')
        : v === 'threshold'
          ? t('monitors.rule_type_threshold')
          : t('monitors.rule_type_pattern'),
  }));

  const notifyMethodOptions = NOTIFY_METHOD_VALUES.map((v) => ({
    value: v,
    label:
      v === 'desktop'
        ? t('monitors.notify_desktop')
        : v === 'sound'
          ? t('monitors.notify_sound')
          : v === 'webhook'
            ? t('monitors.notify_webhook')
            : t('monitors.notify_email'),
  }));

  const ruleTypeLabel = (val: string) => {
    const opt = ruleTypeOptions.find((o) => o.value === val);
    return opt?.label || val;
  };

  const notifyMethodLabel = (m: string) => {
    const opt = notifyMethodOptions.find((o) => o.value === m);
    return opt?.label || m;
  };

  const loadAlertRules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchAlertRules({ page: 1, page_size: 100 });
      setAlertRules(res.results || []);
    } catch {
      msg.error(t('monitors.msg_load_alert_rules_failed'));
    } finally {
      setLoading(false);
    }
  }, [msg, t]);

  useEffect(() => {
    loadAlertRules();
  }, [loadAlertRules]);

  const handleCreate = async (values: Record<string, unknown>) => {
    try {
      const quietHours = values.quiet_hours as Array<{ format: (fmt: string) => string } | undefined> | undefined;
      const payload = {
        ...values,
        quiet_start: quietHours?.[0]?.format('HH:mm') || null,
        quiet_end: quietHours?.[1]?.format('HH:mm') || null,
        notify_methods: (values.notify_methods as string[]) || [],
      };
      if (editingRule?.id) {
        await updateAlertRule(editingRule.id, payload);
        msg.success(t('monitors.msg_alert_rule_updated'));
      } else {
        await createAlertRule(payload);
        msg.success(t('monitors.msg_alert_rule_created'));
      }
      setModalOpen(false);
      setEditingRule(null);
      form.resetFields();
      loadAlertRules();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string; [key: string]: unknown } }; message?: string };
      const data = axiosErr?.response?.data;
      const detail = (data as Record<string, unknown>)?.detail as string | undefined;
      const fieldErrors =
        data && typeof data === 'object'
          ? Object.entries(data)
              .filter(([key]) => key !== 'detail' && Array.isArray((data as Record<string, unknown>)[key]))
              .map(([key, msgs]) => `${key}: ${(msgs as string[]).join(', ')}`)
              .join('\n')
          : '';
      const errMsg = axiosErr instanceof Error ? axiosErr.message : JSON.stringify(data).slice(0, 200);
      console.error('[AlertRules] operation failed:', { err, data, fieldErrors });
      if (detail) {
        msg.error(t('monitors.msg_operation_failed_detail', { detail }));
      } else if (fieldErrors) {
        msg.error(t('monitors.msg_operation_failed_detail', { detail: fieldErrors.split('\n')[0] }));
      } else {
        msg.error(t('monitors.msg_operation_failed_detail', { detail: errMsg || t('monitors.msg_unknown_error') }));
      }
    }
  };

  const handleEdit = (record: AlertRule) => {
    setEditingRule(record);
    form.setFieldsValue({
      ...record,
      quiet_hours:
        record.quiet_start && record.quiet_end
          ? [dayjs(record.quiet_start, 'HH:mm'), dayjs(record.quiet_end, 'HH:mm')]
          : undefined,
    });
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteAlertRule(id);
      msg.success(t('monitors.msg_deleted'));
      loadAlertRules();
    } catch {
      msg.error(t('monitors.msg_delete_failed'));
    }
  };

  const handleToggleEnabled = async (id: number, enabled: boolean) => {
    try {
      await updateAlertRule(id, { enabled });
      setAlertRules((prev) => prev.map((r) => (r.id === id ? { ...r, enabled } : r)));
      msg.success(enabled ? t('monitors.msg_enabled') : t('monitors.msg_disabled'));
    } catch {
      msg.error(t('monitors.msg_operation_failed'));
    }
  };

  const columns: ColumnsType<AlertRule> = [
    { title: t('monitors.col_rule_name'), dataIndex: 'name', key: 'name' },
    {
      title: t('monitors.col_rule_type'),
      dataIndex: 'rule_type',
      key: 'rule_type',
      render: (val: string) => ruleTypeLabel(val),
    },
    { title: t('monitors.col_threshold'), dataIndex: 'threshold', key: 'threshold', width: 80 },
    {
      title: t('monitors.col_notify_methods'),
      dataIndex: 'notify_methods',
      key: 'notify_methods',
      render: (methods: string[]) => (
        <Space wrap>
          {(methods || []).map((m: string) => (
            <Tag key={m} color="blue">
              {notifyMethodLabel(m)}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: t('monitors.col_quiet_hours'),
      key: 'quiet_hours',
      render: (_: unknown, record: AlertRule) =>
        record.quiet_start && record.quiet_end ? `${record.quiet_start} ~ ${record.quiet_end}` : '—',
    },
    {
      title: t('monitors.col_enabled'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record: AlertRule) => (
        <Switch checked={enabled} size="small" onChange={(checked) => handleToggleEnabled(record.id, checked)} />
      ),
    },
    {
      title: t('monitors.col_action'),
      key: 'action',
      width: 120,
      render: (_, record) => (
        <div className="gaf-flex-center gaf-gap-xs">
          <Tooltip key="edit-alert" title={t('monitors.action_edit')}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              aria-label={t('monitors.action_edit_alert_rule')}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Popconfirm key="delete-alert" title={t('monitors.confirm_delete')} onConfirm={() => handleDelete(record.id)}>
            <Button type="link" danger size="small">
              {t('monitors.action_delete')}
            </Button>
          </Popconfirm>
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="gaf-mb-lg">
        <Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingRule(null);
              form.resetFields();
              setModalOpen(true);
            }}
          >
            {t('monitors.btn_new_alert_rule')}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadAlertRules}>
            {t('monitors.btn_refresh')}
          </Button>
        </Space>
      </div>
      <Table columns={columns} dataSource={alertRules || []} rowKey="id" loading={loading} size="small" />
      <Modal
        title={editingRule ? t('monitors.title_edit_alert_rule') : t('monitors.title_new_alert_rule')}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditingRule(null);
        }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Form.Item name="name" label={t('monitors.form_rule_name')} rules={[{ required: true }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="rule_type" label={t('monitors.form_rule_type')} rules={[{ required: true }]}>
            <Select options={ruleTypeOptions} />
          </Form.Item>
          <Form.Item
            name="threshold"
            label={t('monitors.form_threshold')}
            initialValue={3}
            rules={[{ required: true }]}
          >
            <InputNumber className="gaf-w-full" min={1} max={100} />
          </Form.Item>
          <Form.Item name="notify_methods" label={t('monitors.form_notify_methods')} initialValue={[]}>
            <Select
              mode="multiple"
              options={notifyMethodOptions}
              placeholder={t('monitors.placeholder_select_notify')}
            />
          </Form.Item>
          <Form.Item name="quiet_hours" label={t('monitors.form_quiet_hours')}>
            <TimePicker.RangePicker format="HH:mm" className="gaf-w-full" />
          </Form.Item>
          <Form.Item name="enabled" label={t('monitors.form_enabled')} valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

interface EventsTabProps {
  isSilenced: boolean;
  refreshKey: number;
}

function EventsTab({ isSilenced, refreshKey }: EventsTabProps) {
  const t = useTranslation();
  const { message: msg } = App.useApp();
  const { token } = antTheme.useToken();
  const [events, setEvents] = useState<MonitorEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [severityFilter, setSeverityFilter] = useState<MonitorEventSeverity | undefined>();
  const [statusFilter, setStatusFilter] = useState<'unhandled' | 'acknowledged' | 'escalated' | undefined>();

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page: 1, page_size: 50 };
      if (severityFilter) params.severity = severityFilter;
      const res = await fetchMonitorEvents(params as Parameters<typeof fetchMonitorEvents>[0]);
      setEvents(res.results || []);
    } catch {
      msg.error(t('monitors.msg_load_events_failed'));
    } finally {
      setLoading(false);
    }
  }, [severityFilter, msg, t]);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  useEffect(() => {
    if (refreshKey > 0) loadEvents();
  }, [refreshKey, loadEvents]);

  const handleAcknowledge = async (eventId: number) => {
    try {
      const updated = await acknowledgeEvent(eventId);
      setEvents((prev) => prev.map((e) => (e.id === eventId ? updated : e)));
      msg.success(t('monitors.msg_event_acknowledged'));
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } };
      const detail = axiosErr?.response?.data?.detail;
      if (axiosErr?.response?.status === 409) {
        msg.warning(detail || t('monitors.msg_event_already_ack'));
        // re- pull with sync status
        loadEvents();
      } else {
        msg.error(detail ? t('monitors.msg_ack_failed_detail', { detail }) : t('monitors.msg_ack_failed_retry'));
      }
    }
  };

  const statusFilteredEvents = statusFilter
    ? events.filter((e) => {
        if (statusFilter === 'unhandled') return !e.acknowledged_at && !e.escalated_at;
        if (statusFilter === 'acknowledged') return !!e.acknowledged_at && !e.escalated_at;
        if (statusFilter === 'escalated') return !!e.escalated_at;
        return true;
      })
    : events;

  const displayedEvents = isSilenced ? statusFilteredEvents.filter((e) => e.severity === 'P3') : statusFilteredEvents;

  const severityLabel = (severity: MonitorEventSeverity) => {
    if (severity === 'P0') return t('monitors.severity_P0');
    if (severity === 'P1') return t('monitors.severity_P1');
    if (severity === 'P2') return t('monitors.severity_P2');
    return t('monitors.severity_P3');
  };

  const columns: ColumnsType<MonitorEvent> = [
    { title: t('monitors.col_event_type'), dataIndex: 'event_type', key: 'event_type', width: 140, ellipsis: true },
    { title: t('monitors.col_agent'), dataIndex: 'agent', key: 'agent', width: 70 },
    {
      title: t('monitors.col_severity'),
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: MonitorEventSeverity) => (
        <Tag color={SEVERITY_COLOR_MAP[severity] || 'default'}>{severityLabel(severity)}</Tag>
      ),
    },
    { title: t('monitors.col_detail'), dataIndex: 'handling_result', key: 'handling_result', ellipsis: true },
    {
      title: t('monitors.col_ack_status'),
      key: 'ack_status',
      width: 110,
      render: (_, record) => {
        if (record.escalated_at) {
          return (
            <Tag icon={<RiseOutlined />} color="red">
              {t('monitors.ack_escalated')}
            </Tag>
          );
        }
        if (record.acknowledged_at) {
          return (
            <Tag icon={<CheckCircleOutlined />} color="green">
              {t('monitors.ack_confirmed')}
            </Tag>
          );
        }
        return <Tag color="default">{t('monitors.ack_unhandled')}</Tag>;
      },
    },
    {
      title: t('monitors.col_ack_by'),
      dataIndex: 'acknowledged_by_username',
      key: 'acknowledged_by_username',
      width: 100,
      render: (val: string | null | undefined, record) =>
        record.acknowledged_at ? (
          <Tooltip title={t('monitors.tooltip_ack_time') + formatDateTime(record.acknowledged_at)}>
            <span>
              <UserOutlined /> {val || '-'}
            </span>
          </Tooltip>
        ) : (
          <span style={{ color: token.colorTextTertiary }}>-</span>
        ),
    },
    {
      title: t('monitors.col_escalated_at'),
      dataIndex: 'escalated_at',
      key: 'escalated_at',
      width: 170,
      render: (val: string | null | undefined) =>
        val ? (
          <Tooltip title={t('monitors.tooltip_escalate')}>
            <Tag icon={<RiseOutlined />} color="red">
              {formatDateTime(val)}
            </Tag>
          </Tooltip>
        ) : (
          <span style={{ color: token.colorTextTertiary }}>-</span>
        ),
    },
    {
      title: t('monitors.col_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (val: string) => formatDateTime(val),
    },
    {
      title: t('monitors.col_action'),
      key: 'action',
      width: 90,
      fixed: 'right',
      render: (_, record) =>
        record.acknowledged_at ? null : (
          <Tooltip title={t('monitors.tooltip_ack_event')}>
            <Button
              type="link"
              size="small"
              icon={<CheckCircleOutlined />}
              aria-label={t('monitors.aria_ack_event')}
              onClick={() => handleAcknowledge(record.id)}
            >
              {t('monitors.btn_acknowledge')}
            </Button>
          </Tooltip>
        ),
    },
  ];

  return (
    <>
      <div className="gaf-mb-lg gaf-flex-between">
        <Space>
          <Select
            placeholder={t('monitors.placeholder_filter_severity')}
            allowClear
            style={{ width: 130 }}
            value={severityFilter}
            onChange={setSeverityFilter}
            options={[
              { value: 'P0', label: t('monitors.severity_P0') },
              { value: 'P1', label: t('monitors.severity_P1') },
              { value: 'P2', label: t('monitors.severity_P2') },
              { value: 'P3', label: t('monitors.severity_P3') },
            ]}
          />
          <Select
            placeholder={t('monitors.placeholder_filter_status')}
            allowClear
            style={{ width: 140 }}
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: 'unhandled', label: t('monitors.ack_unhandled') },
              { value: 'acknowledged', label: t('monitors.ack_confirmed') },
              { value: 'escalated', label: t('monitors.ack_escalated') },
            ]}
          />
        </Space>
        <Button icon={<ReloadOutlined />} onClick={loadEvents}>
          {t('monitors.btn_refresh')}
        </Button>
      </div>
      {isSilenced && <Alert type="info" title={t('monitors.silence_hint')} showIcon className="gaf-mb-md" closable />}
      <Table columns={columns} dataSource={displayedEvents || []} rowKey="id" loading={loading} size="small" />
    </>
  );
}

/** system diagnostics Tab (P-030) */
function DiagnoseTab() {
  const t = useTranslation();
  const { message: msg } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [diagnoseResult, setDiagnoseResult] = useState<{
    overall: string;
    total_issues: number;
    error_count: number;
    warning_count: number;
    fixable_count: number;
    results: Array<{
      category: string;
      name?: string;
      status: string;
      message: string;
      fixable?: boolean;
    }>;
  } | null>(null);
  const [fixResult, setFixResult] = useState<{
    success: boolean;
    fixed: Array<{ category: string; message: string }>;
    failed: Array<{ category: string; message: string }>;
  } | null>(null);

  const handleDiagnose = useCallback(async () => {
    setLoading(true);
    setFixResult(null);
    try {
      const res = await diagnose();
      setDiagnoseResult(res);
      if (res.overall === 'ok') {
        msg.success(t('monitors.msg_diagnose_pass'));
      }
    } catch {
      msg.error(t('monitors.msg_diagnose_failed'));
    } finally {
      setLoading(false);
    }
  }, [msg, t]);

  const handleFix = useCallback(async () => {
    setFixing(true);
    setFixResult(null);
    try {
      const res = await autoFix();
      setFixResult(res);
      if (res.success) {
        msg.success(t('monitors.msg_fix_completed'));
      } else {
        msg.warning(t('monitors.msg_fix_partial', { count: res.failed.length }));
      }
      // diagnostics after auto refresh
      handleDiagnose();
    } catch {
      msg.error(t('monitors.msg_fix_failed'));
    } finally {
      setFixing(false);
    }
  }, [msg, handleDiagnose, t]);

  useEffect(() => {
    handleDiagnose();
  }, [handleDiagnose]);

  const statusColor: Record<string, string> = { ok: 'green', warning: 'orange', error: 'red' };
  const statusLabel = (status: string) => {
    if (status === 'ok') return t('monitors.diag_status_ok');
    if (status === 'warning') return t('monitors.diag_status_warning');
    return t('monitors.diag_status_error');
  };

  const columns: ColumnsType<{ category: string; name?: string; status: string; message: string; fixable?: boolean }> =
    [
      {
        title: t('monitors.col_check_item'),
        dataIndex: 'name',
        key: 'name',
        width: 150,
      },
      {
        title: t('monitors.col_status'),
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (status: string) => <Tag color={statusColor[status]}>{statusLabel(status)}</Tag>,
      },
      {
        title: t('monitors.col_detail'),
        dataIndex: 'message',
        key: 'message',
      },
      {
        title: t('monitors.col_action'),
        key: 'action',
        width: 100,
        render: (_, record) =>
          record.fixable ? (
            <Button type="link" size="small" onClick={handleFix} loading={fixing}>
              {t('monitors.btn_one_click_fix')}
            </Button>
          ) : null,
      },
    ];

  return (
    <div>
      <div className="gaf-mb-lg">
        <Space>
          <Button
            type="primary"
            icon={
              <span aria-hidden="true">
                <MedicineBoxOutlined />
              </span>
            }
            onClick={handleDiagnose}
            loading={loading}
          >
            {t('monitors.btn_diagnose')}
          </Button>
          <Button
            icon={<ThunderboltOutlined />}
            onClick={handleFix}
            loading={fixing}
            disabled={!diagnoseResult || diagnoseResult.fixable_count === 0}
          >
            {t('monitors.btn_fix')}
          </Button>
        </Space>
      </div>

      {diagnoseResult && (
        <Space className="gaf-mb-lg">
          <Tag
            color={diagnoseResult.overall === 'ok' ? 'green' : diagnoseResult.overall === 'warning' ? 'orange' : 'red'}
          >
            {t('monitors.diag_overall')}
            {statusLabel(diagnoseResult.overall) || diagnoseResult.overall}
          </Tag>
          {diagnoseResult.error_count > 0 && (
            <Tag color="red">{t('monitors.diag_error_count', { count: diagnoseResult.error_count })}</Tag>
          )}
          {diagnoseResult.warning_count > 0 && (
            <Tag color="orange">{t('monitors.diag_warning_count', { count: diagnoseResult.warning_count })}</Tag>
          )}
          {diagnoseResult.fixable_count > 0 && (
            <Tag color="blue">{t('monitors.diag_fixable_count', { count: diagnoseResult.fixable_count })}</Tag>
          )}
        </Space>
      )}

      {fixResult && (
        <div className="gaf-mb-lg">
          {fixResult.fixed.map((item, idx) => (
            <Alert key={`fixed-${idx}`} type="success" title={item.message} className="gaf-mb-sm" closable />
          ))}
          {fixResult.failed.map((item, idx) => (
            <Alert key={`failed-${idx}`} type="error" title={item.message} className="gaf-mb-sm" closable />
          ))}
        </div>
      )}

      <Table
        columns={columns}
        dataSource={diagnoseResult?.results || []}
        rowKey="category"
        loading={loading}
        size="small"
        pagination={false}
      />
    </div>
  );
}

export default MonitorsPage;
