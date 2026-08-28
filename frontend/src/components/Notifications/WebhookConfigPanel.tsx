/**
 * Webhook config panel component
 * management Webhook list, add, edit, delete and test operation
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Table, Button, Modal, Form, Input, Checkbox, Tag, Space, Popconfirm, message, Card, Switch } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SendOutlined } from '@ant-design/icons';
import { fetchWebhooks } from '@/api/misc';
import { useTranslation } from '@/i18n';

/** Webhook data type */
interface WebhookItem {
  id: number;
  name: string;
  url: string;
  event_types: string[];
  is_enabled: boolean;
  secret_key: string;
}

/** event type value list (labels resolved via i18n at render time). */
const EVENT_TYPE_VALUES = [
  'task_completed',
  'alert_triggered',
  'device_offline',
  'account_anomaly',
  'system_update',
] as const;

/** Map event_type value → i18n key. */
const EVENT_TYPE_LABEL_KEY: Record<string, string> = {
  task_completed: 'notifications.webhook_event_task_completed',
  alert_triggered: 'notifications.webhook_event_alert_triggered',
  device_offline: 'notifications.webhook_event_device_offline',
  account_anomaly: 'notifications.webhook_event_account_anomaly',
  system_update: 'notifications.webhook_event_system_update',
};

export function WebhookConfigPanel() {
  const t = useTranslation();
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form] = Form.useForm();
  const [testLoading, setTestLoading] = useState<Record<number, boolean>>({});
  /** Track the test-send delay timer so it can be cleaned up on unmount */
  const testTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** event type options with localized labels. Memoized on t for locale switches. */
  const eventTypeOptions = useMemo(
    () =>
      EVENT_TYPE_VALUES.map((value) => ({
        label: t(EVENT_TYPE_LABEL_KEY[value]),
        value,
      })),
    [t],
  );

  /** Clear any pending test timer on unmount */
  useEffect(() => {
    return () => {
      if (testTimerRef.current) clearTimeout(testTimerRef.current);
    };
  }, []);

  /** component mount when from API load Webhook list */
  useEffect(() => {
    const loadWebhooks = async () => {
      try {
        const data = await fetchWebhooks<WebhookItem[]>();
        setWebhooks(data);
      } catch {
        // API unavailable when keep empty list
      }
    };
    loadWebhooks();
  }, []);

  /** open added modal */
  const handleAdd = useCallback(() => {
    setEditingId(null);
    form.resetFields();
    form.setFieldsValue({
      event_types: [],
      is_enabled: true,
    });
    setModalOpen(true);
  }, [form]);

  /** open edit modal */
  const handleEdit = useCallback(
    (record: WebhookItem) => {
      setEditingId(record.id);
      form.setFieldsValue({
        name: record.name,
        url: record.url,
        event_types: record.event_types,
        secret_key: '',
        is_enabled: record.is_enabled,
      });
      setModalOpen(true);
    },
    [form],
  );

  /** submit form ( added or edit ) */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingId !== null) {
        setWebhooks((prev) =>
          prev.map((w) =>
            w.id === editingId
              ? {
                  ...w,
                  name: values.name,
                  url: values.url,
                  event_types: values.event_types,
                  is_enabled: values.is_enabled,
                  ...(values.secret_key ? { secret_key: values.secret_key.replace(/./g, '*') } : {}),
                }
              : w,
          ),
        );
        message.success(t('notifications.webhook_update_success'));
      } else {
        const newWebhook: WebhookItem = {
          id: Date.now(),
          name: values.name,
          url: values.url,
          event_types: values.event_types,
          is_enabled: values.is_enabled,
          secret_key: values.secret_key ? values.secret_key.replace(/./g, '*') : '',
        };
        setWebhooks((prev) => [...prev, newWebhook]);
        message.success(t('notifications.webhook_add_success'));
      }
      setModalOpen(false);
    } catch (err) {
      console.error('Webhook config load failed:', err);
    }
  };

  /** delete Webhook */
  const handleDelete = (id: number) => {
    setWebhooks((prev) => prev.filter((w) => w.id !== id));
    message.success(t('notifications.webhook_delete_success'));
  };

  /** test send Webhook */
  const handleTestSend = async (record: WebhookItem) => {
    setTestLoading((prev) => ({ ...prev, [record.id]: true }));
    if (testTimerRef.current) clearTimeout(testTimerRef.current);
    try {
      await new Promise<void>((resolve) => {
        testTimerRef.current = setTimeout(resolve, 1500);
      });
      message.success(t('notifications.webhook_test_sent', { name: record.name }));
    } catch {
      message.error(t('notifications.webhook_send_failed'));
    } finally {
      setTestLoading((prev) => ({ ...prev, [record.id]: false }));
    }
  };

  /** get event type label list */
  const renderEventTypes = (types: string[]) =>
    types.map((type) => {
      const labelKey = EVENT_TYPE_LABEL_KEY[type];
      return (
        <Tag key={type} color="blue">
          {labelKey ? t(labelKey) : type}
        </Tag>
      );
    });

  /** table column definitions. Not memoized — matches original pattern; the
   *  render closures capture t/handlers which change every render anyway. */
  const columns = [
    {
      title: t('notifications.webhook_col_name'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <strong>{name}</strong>,
    },
    {
      title: 'URL',
      dataIndex: 'url',
      key: 'url',
      ellipsis: true,
      render: (url: string) => (
        <span className="gaf-text-sm" style={{ color: '#666' }}>
          {url}
        </span>
      ),
    },
    {
      title: t('notifications.webhook_col_event_types'),
      dataIndex: 'event_types',
      key: 'event_types',
      width: 240,
      render: (_: unknown, record: WebhookItem) => (
        <Space size={[4, 4]} wrap>
          {renderEventTypes(record.event_types)}
        </Space>
      ),
    },
    {
      title: t('notifications.webhook_col_status'),
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 80,
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'green' : 'default'}>
          {enabled ? t('notifications.webhook_status_enabled') : t('notifications.webhook_status_disabled')}
        </Tag>
      ),
    },
    {
      title: t('notifications.webhook_col_action'),
      key: 'action',
      width: 220,
      render: (_: unknown, record: WebhookItem) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<SendOutlined />}
            loading={testLoading[record.id]}
            onClick={() => handleTestSend(record)}
          >
            {t('notifications.webhook_btn_test')}
          </Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            {t('notifications.webhook_btn_edit')}
          </Button>
          <Popconfirm title={t('notifications.webhook_confirm_delete')} onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              {t('notifications.webhook_btn_delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={t('notifications.tab_webhooks')}
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          {t('notifications.webhook_btn_add')}
        </Button>
      }
    >
      <Table dataSource={webhooks || []} columns={columns} rowKey="id" pagination={false} size="middle" />

      <Modal
        open={modalOpen}
        title={
          editingId !== null ? t('notifications.webhook_modal_edit_title') : t('notifications.webhook_modal_add_title')
        }
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        destroyOnHidden
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label={t('notifications.webhook_form_name_label')}
            name="name"
            rules={[{ required: true, message: t('notifications.webhook_form_name_required') }]}
          >
            <Input placeholder={t('notifications.webhook_form_name_placeholder')} />
          </Form.Item>

          <Form.Item
            label="URL"
            name="url"
            rules={[
              { required: true, message: t('notifications.webhook_form_url_required') },
              { type: 'url', message: t('notifications.webhook_form_url_invalid') },
            ]}
          >
            <Input placeholder="https://example.com/webhook" />
          </Form.Item>

          <Form.Item
            label={t('notifications.webhook_form_event_types_label')}
            name="event_types"
            rules={[
              {
                required: true,
                message: t('notifications.webhook_form_event_types_required'),
              },
            ]}
          >
            <Checkbox.Group options={eventTypeOptions} />
          </Form.Item>

          <Form.Item label={t('notifications.webhook_form_secret_key_label')} name="secret_key">
            <Input.Password placeholder={t('notifications.webhook_form_secret_key_placeholder')} />
          </Form.Item>

          <Form.Item label={t('notifications.webhook_form_enabled_label')} name="is_enabled" valuePropName="checked">
            <Switch
              checkedChildren={t('notifications.webhook_switch_enabled')}
              unCheckedChildren={t('notifications.webhook_switch_disabled')}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

export default WebhookConfigPanel;
