/**
 * Notification preferences component
 * Provides notification toggles, quiet hours, retention days, and webhook channel config (P-018)
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Form,
  Switch,
  TimePicker,
  Select,
  Button,
  Space,
  Card,
  Divider,
  message,
  Table,
  Modal,
  Input,
  Popconfirm,
  Tag,
  Tooltip,
} from 'antd';
import { SaveOutlined, UndoOutlined, PlusOutlined, EditOutlined, SendOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import {
  fetchNotificationPreferences,
  saveNotificationPreferences,
  fetchWebhooks,
  createWebhook,
  updateWebhook,
  deleteWebhook,
  testWebhook,
} from '@/api/misc';
import { classifyError } from '@/utils/errorHandler';
import { useTranslation } from '@/i18n';

/** Notification preference data type */
interface NotificationPreference {
  desktop_notification: boolean;
  sound_alert: boolean;
  system_notification: boolean;
  alert_notification: boolean;
  community_notification: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  retention_days: number;
}

/** Webhook config data type matching backend WebhookConfig model */
interface WebhookConfigItem {
  id?: number;
  channel: string;
  url: string;
  is_active: boolean;
  created_at?: string;
}

/** Webhook channel option value (label resolved via t() at call sites) */
interface ChannelOption {
  value: string;
  labelKey: string;
}

export function NotificationPreferences() {
  const t = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [originalValues, setOriginalValues] = useState<Partial<NotificationPreference> | null>(null);

  /** Retention day options (i18n-aware) */
  const RETENTION_OPTIONS = useMemo(
    () => [
      { label: t('notifications.pref_retention_days', { count: 7 }), value: 7 },
      { label: t('notifications.pref_retention_days', { count: 15 }), value: 15 },
      { label: t('notifications.pref_retention_days', { count: 30 }), value: 30 },
      { label: t('notifications.pref_retention_days', { count: 60 }), value: 60 },
      { label: t('notifications.pref_retention_days', { count: 90 }), value: 90 },
    ],
    [t],
  );

  /** Available webhook channel options (labels resolved via t()) */
  const CHANNEL_OPTIONS: ChannelOption[] = useMemo(
    () => [
      { value: 'dingtalk', labelKey: 'notifications.pref_channel_dingtalk' },
      { value: 'feishu', labelKey: 'notifications.pref_channel_feishu' },
      { value: 'wechat_work', labelKey: 'notifications.pref_channel_wechat_work' },
      { value: 'slack', labelKey: 'Slack' },
      { value: 'generic', labelKey: 'notifications.pref_channel_generic' },
    ],
    [],
  );

  /** Resolve a channel value to a localized label (falls back to raw value). */
  const resolveChannelLabel = useCallback(
    (value: string) => {
      const opt = CHANNEL_OPTIONS.find((o) => o.value === value);
      if (!opt) return value;
      // Brand names like "Slack" are not i18n keys — render verbatim.
      return opt.labelKey.includes('.') ? t(opt.labelKey) : opt.labelKey;
    },
    [CHANNEL_OPTIONS, t],
  );

  useEffect(() => {
    loadPreferences();
    loadWebhooks();
  }, []);

  /** Load current notification preferences */
  const loadPreferences = async () => {
    setLoading(true);
    try {
      const data = await fetchNotificationPreferences<Partial<NotificationPreference> | Record<string, unknown>>();
      const prefs = (data || {}) as Record<string, unknown>;
      form.setFieldsValue({
        desktop_notification: prefs.desktop_notification ?? true,
        sound_alert: prefs.sound_alert ?? false,
        system_notification: prefs.system_notification ?? false,
        alert_notification: prefs.alert_notification ?? true,
        community_notification: prefs.community_notification ?? false,
        quiet_hours:
          prefs.quiet_hours_start && prefs.quiet_hours_end
            ? [dayjs(prefs.quiet_hours_start as string, 'HH:mm'), dayjs(prefs.quiet_hours_end as string, 'HH:mm')]
            : [dayjs('22:00', 'HH:mm'), dayjs('08:00', 'HH:mm')],
        retention_days: prefs.retention_days ?? 30,
      });
      setOriginalValues(prefs as Partial<NotificationPreference>);
    } catch {
      message.error(t('notifications.pref_load_failed'));
    } finally {
      setLoading(false);
    }
  };

  /** Save notification preferences */
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const payload = {
        desktop_notification: values.desktop_notification,
        sound_alert: values.sound_alert,
        system_notification: values.system_notification,
        alert_notification: values.alert_notification,
        community_notification: values.community_notification,
        quiet_hours_start:
          Array.isArray(values.quiet_hours) && values.quiet_hours[0] ? values.quiet_hours[0].format('HH:mm') : '22:00',
        quiet_hours_end:
          Array.isArray(values.quiet_hours) && values.quiet_hours[1] ? values.quiet_hours[1].format('HH:mm') : '08:00',
        retention_days: values.retention_days,
      };
      await saveNotificationPreferences(payload);
      message.success(t('notifications.pref_save_success'));
    } catch (err: unknown) {
      const classified = classifyError(err);
      if ((classified.originalError as { errorFields?: unknown[] }).errorFields) return;
      message.error(t('notifications.pref_save_failed', { message: classified.message }));
    } finally {
      setSaving(false);
    }
  };

  /** Reset and restore original values */
  const handleReset = useCallback(() => {
    if (originalValues) {
      form.setFieldsValue({
        desktop_notification: originalValues.desktop_notification ?? true,
        sound_alert: originalValues.sound_alert ?? false,
        system_notification: originalValues.system_notification ?? false,
        alert_notification: originalValues.alert_notification ?? true,
        community_notification: originalValues.community_notification ?? false,
        quiet_hours:
          originalValues.quiet_hours_start && originalValues.quiet_hours_end
            ? [dayjs(originalValues.quiet_hours_start, 'HH:mm'), dayjs(originalValues.quiet_hours_end, 'HH:mm')]
            : [dayjs('22:00', 'HH:mm'), dayjs('08:00', 'HH:mm')],
        retention_days: originalValues.retention_days ?? 30,
      });
      message.info(t('notifications.pref_reset_success'));
    }
  }, [originalValues, form]);

  /* ==================== Webhook Config Section (P-018) ==================== */

  const [webhooks, setWebhooks] = useState<WebhookConfigItem[]>([]);
  const [whLoading, setWhLoading] = useState(false);
  const [whModalOpen, setWhModalOpen] = useState(false);
  const [editingWebhook, setEditingWebhook] = useState<WebhookConfigItem | null>(null);
  const [whForm] = Form.useForm();
  const [testingId, setTestingId] = useState<number | null>(null);

  /** Load webhook configs from backend */
  const loadWebhooks = async () => {
    setWhLoading(true);
    try {
      const data = await fetchWebhooks<WebhookConfigItem[] | { results: WebhookConfigItem[] }>();
      setWebhooks(
        Array.isArray((data as { results?: WebhookConfigItem[] }).results)
          ? (data as { results: WebhookConfigItem[] }).results
          : Array.isArray(data)
            ? data
            : [],
      );
    } catch {
      // silently ignore on preferences page load
    } finally {
      setWhLoading(false);
    }
  };

  /** Create or update a webhook config */
  const handleSaveWebhook = async (values: Partial<WebhookConfigItem>) => {
    try {
      if (editingWebhook?.id) {
        await updateWebhook<WebhookConfigItem>(editingWebhook.id, values);
        message.success(t('notifications.webhook_update_success'));
      } else {
        await createWebhook<Partial<WebhookConfigItem>>(values);
        message.success(t('notifications.webhook_create_success'));
      }
      setWhModalOpen(false);
      setEditingWebhook(null);
      whForm.resetFields();
      loadWebhooks();
    } catch {
      message.error(t('notifications.webhook_op_failed'));
    }
  };

  /** Delete a webhook config */
  const handleDeleteWebhook = async (id: number) => {
    try {
      await deleteWebhook(id);
      message.success(t('notifications.webhook_delete_success'));
      loadWebhooks();
    } catch {
      message.error(t('notifications.webhook_delete_failed'));
    }
  };

  /** Test sending to a webhook endpoint */
  const handleTestWebhook = async (id: number) => {
    setTestingId(id);
    try {
      const data = await testWebhook<{ status: string; http_status?: number; message?: string; body?: string }>(id);
      if (data.status === 'ok') {
        message.success(t('notifications.webhook_test_success', { status: data.http_status }));
      } else {
        message.error(
          t('notifications.webhook_test_failed', {
            message: data.message || data.body || t('notifications.unknown_error'),
          }),
        );
      }
    } catch {
      message.error(t('notifications.webhook_test_request_failed'));
    } finally {
      setTestingId(null);
    }
  };

  /** Open modal for adding/editing webhook */
  const openWebhookModal = (record?: WebhookConfigItem) => {
    if (record) {
      setEditingWebhook(record);
      whForm.setFieldsValue(record);
    } else {
      setEditingWebhook(null);
      whForm.resetFields();
    }
    setWhModalOpen(true);
  };

  /** Webhook table column definitions */
  const webhookColumns: ColumnsType<WebhookConfigItem> = [
    {
      title: t('notifications.pref_webhook_col_channel'),
      dataIndex: 'channel',
      key: 'channel',
      width: 130,
      render: (ch: string) => <Tag color="blue">{resolveChannelLabel(ch)}</Tag>,
    },
    {
      title: t('notifications.pref_webhook_col_url'),
      dataIndex: 'url',
      key: 'url',
      ellipsis: true,
      render: (url: string) => (
        <Tooltip title={url}>
          <span style={{ maxWidth: 250, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {url}
          </span>
        </Tooltip>
      ),
    },
    {
      title: t('notifications.pref_webhook_col_status'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (active: boolean) => (
        <Tag color={active ? 'green' : 'default'}>
          {active ? t('notifications.pref_webhook_status_enabled') : t('notifications.pref_webhook_status_disabled')}
        </Tag>
      ),
    },
    {
      title: t('notifications.pref_webhook_col_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (val: string) => (val ? new Date(val).toLocaleString() : '-'),
    },
    {
      title: t('notifications.pref_webhook_col_action'),
      key: 'action',
      width: 180,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title={t('notifications.pref_webhook_action_edit')}>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              aria-label={t('notifications.pref_webhook_action_edit')}
              onClick={() => openWebhookModal(record)}
            />
          </Tooltip>
          <Tooltip title={t('notifications.pref_webhook_action_test')}>
            <Button
              type="link"
              size="small"
              icon={<SendOutlined />}
              aria-label={t('notifications.pref_webhook_action_test')}
              loading={testingId === record.id}
              onClick={() => record.id && handleTestWebhook(record.id)}
            />
          </Tooltip>
          <Popconfirm
            title={t('notifications.pref_webhook_confirm_delete')}
            onConfirm={() => record.id && handleDeleteWebhook(record.id)}
          >
            <Button type="link" danger size="small">
              {t('notifications.pref_webhook_action_delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className="gaf-flex-col gaf-gap-lg">
      {/* Original notification preferences card */}
      <Card title={t('notifications.pref_card_title')} loading={loading}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            desktop_notification: true,
            sound_alert: true,
            system_notification: false,
            alert_notification: true,
            community_notification: false,
            retention_days: 30,
          }}
        >
          <Divider>{t('notifications.pref_divider_methods')}</Divider>

          <Form.Item label={t('notifications.pref_label_desktop')} name="desktop_notification" valuePropName="checked">
            <Switch
              checkedChildren={t('notifications.pref_switch_on')}
              unCheckedChildren={t('notifications.pref_switch_off')}
            />
          </Form.Item>

          <Form.Item label={t('notifications.pref_label_sound')} name="sound_alert" valuePropName="checked">
            <Switch
              checkedChildren={t('notifications.pref_switch_on')}
              unCheckedChildren={t('notifications.pref_switch_off')}
            />
          </Form.Item>

          <Form.Item label={t('notifications.pref_label_system')} name="system_notification" valuePropName="checked">
            <Switch
              checkedChildren={t('notifications.pref_switch_on')}
              unCheckedChildren={t('notifications.pref_switch_off')}
            />
          </Form.Item>

          <Divider>{t('notifications.pref_divider_scope')}</Divider>

          <Form.Item label={t('notifications.pref_label_alert')} name="alert_notification" valuePropName="checked">
            <Switch
              checkedChildren={t('notifications.pref_switch_on')}
              unCheckedChildren={t('notifications.pref_switch_off')}
            />
          </Form.Item>

          <Form.Item
            label={t('notifications.pref_label_community')}
            name="community_notification"
            valuePropName="checked"
          >
            <Switch
              checkedChildren={t('notifications.pref_switch_on')}
              unCheckedChildren={t('notifications.pref_switch_off')}
            />
          </Form.Item>

          <Divider titlePlacement="left">{t('notifications.pref_divider_advanced')}</Divider>

          <Form.Item label={t('notifications.pref_label_quiet_hours')} name="quiet_hours">
            <TimePicker.RangePicker format="HH:mm" minuteStep={30} />
          </Form.Item>

          <Form.Item label={t('notifications.pref_label_retention')} name="retention_days">
            <Select options={RETENTION_OPTIONS} className="gaf-w-200" />
          </Form.Item>

          <Divider />

          <Form.Item>
            <Space>
              <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
                {t('notifications.pref_btn_save')}
              </Button>
              <Button icon={<UndoOutlined />} onClick={handleReset}>
                {t('notifications.pref_btn_reset')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {/* Webhook channel configuration card (P-018) */}
      <Card
        title={t('notifications.pref_webhook_card_title')}
        extra={
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => openWebhookModal()}>
            {t('notifications.pref_webhook_btn_add')}
          </Button>
        }
      >
        <Table
          columns={webhookColumns}
          dataSource={webhooks}
          rowKey="id"
          loading={whLoading}
          size="small"
          pagination={false}
          locale={{ emptyText: t('notifications.pref_webhook_empty') }}
        />
      </Card>

      {/* Webhook add/edit modal */}
      <Modal
        title={
          editingWebhook
            ? t('notifications.pref_webhook_modal_edit_title')
            : t('notifications.pref_webhook_modal_add_title')
        }
        open={whModalOpen}
        onCancel={() => {
          setWhModalOpen(false);
          setEditingWebhook(null);
        }}
        onOk={() => whForm.submit()}
        width={560}
        destroyOnHidden
      >
        <Form form={whForm} onFinish={handleSaveWebhook} layout="vertical">
          <Form.Item
            name="channel"
            label={t('notifications.pref_webhook_form_channel_label')}
            rules={[{ required: true, message: t('notifications.pref_webhook_form_channel_required') }]}
          >
            <Select
              options={CHANNEL_OPTIONS.map((o) => ({
                value: o.value,
                label: o.labelKey.includes('.') ? t(o.labelKey) : o.labelKey,
              }))}
              placeholder={t('notifications.pref_webhook_form_channel_placeholder')}
            />
          </Form.Item>
          <Form.Item
            name="url"
            label={t('notifications.pref_webhook_form_url_label')}
            rules={[
              { required: true, message: t('notifications.pref_webhook_form_url_required') },
              { type: 'url', message: t('notifications.pref_webhook_form_url_invalid') },
            ]}
          >
            <Input placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
          </Form.Item>
          <Form.Item
            name="is_active"
            label={t('notifications.pref_webhook_form_enabled_label')}
            valuePropName="checked"
            initialValue={true}
          >
            <Switch
              checkedChildren={t('notifications.pref_webhook_switch_enabled')}
              unCheckedChildren={t('notifications.pref_webhook_switch_disabled')}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default NotificationPreferences;
