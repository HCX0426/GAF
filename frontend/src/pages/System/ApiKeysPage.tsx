/**
 * API Key management page
 * CRUD for API keys: name, permissions, IP whitelist, call count,
 * expiration, active status
 */
import { useEffect, useState, useCallback } from 'react';
import {
  Table,
  Button,
  Space,
  Tag,
  Popconfirm,
  Card,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  DatePicker,
  App as AntApp,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, KeyOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchApiKeys, createApiKey, updateApiKey, deleteApiKey } from '@/api/accounts';
import type { ApiKey } from '@/types/models';
import { useTranslation, getLocale } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

export function ApiKeysPage() {
  const { message, modal } = AntApp.useApp();
  const t = useTranslation();
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [searchText, setSearchText] = useState('');

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<ApiKey | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const isEdit = !!editingKey;

  /** Fill form data when editing, reset when creating */
  useEffect(() => {
    if (editorOpen && editingKey) {
      form.setFieldsValue({
        name: editingKey.name,
        permissions: Object.keys(editingKey.permissions || {}),
        ip_whitelist: editingKey.ip_whitelist || [],
        expires_at: editingKey.expires_at ? dayjs(editingKey.expires_at) : null,
        is_active: editingKey.is_active,
      });
    } else if (editorOpen) {
      form.resetFields();
      form.setFieldsValue({
        is_active: true,
      });
    }
  }, [editorOpen, editingKey, form]);

  const loadApiKeys = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchApiKeys({
        page,
        page_size: pageSize,
        search: searchText || undefined,
      });
      setApiKeys(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      message.error(t('apiKeys.msg_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchText, message, t]);

  useEffect(() => {
    loadApiKeys();
  }, [loadApiKeys]);

  const handleCreate = () => {
    setEditingKey(undefined);
    setEditorOpen(true);
  };

  const handleEdit = (record: ApiKey) => {
    setEditingKey(record);
    setEditorOpen(true);
  };

  const handleClose = () => {
    setEditorOpen(false);
    setEditingKey(undefined);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      // Convert permissions array to object format
      const permissionsObj: Record<string, unknown> = {};
      if (Array.isArray(values.permissions)) {
        values.permissions.forEach((p: string) => {
          permissionsObj[p] = true;
        });
      }

      const data = {
        name: values.name,
        permissions: permissionsObj,
        ip_whitelist: values.ip_whitelist || [],
        expires_at: values.expires_at ? values.expires_at.toISOString() : null,
        is_active: values.is_active,
      };

      setSubmitting(true);

      if (isEdit) {
        await updateApiKey(editingKey!.id, data);
        message.success(t('apiKeys.msg_update_success'));
      } else {
        const result = await createApiKey(data);
        // Show the generated key on create
        if (result.plain_key) {
          modal.info({
            title: t('apiKeys.msg_create_title'),
            width: 600,
            content: (
              <div>
                <p>{t('apiKeys.msg_create_warning')}</p>
                <Input.Password value={result.plain_key} readOnly className="gaf-mt-sm" />
              </div>
            ),
          });
        } else {
          message.success(t('apiKeys.msg_create_success'));
        }
      }

      setEditorOpen(false);
      loadApiKeys();
    } catch {
      message.error(isEdit ? t('apiKeys.msg_update_failed') : t('apiKeys.msg_create_failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (record: ApiKey) => {
    try {
      await deleteApiKey(record.id);
      message.success(t('apiKeys.msg_delete_success'));
      loadApiKeys();
    } catch {
      message.error(t('apiKeys.msg_delete_failed'));
    }
  };

  const handleToggleActive = async (record: ApiKey, checked: boolean) => {
    try {
      await updateApiKey(record.id, { ...record, is_active: checked });
      message.success(checked ? t('apiKeys.msg_toggle_enabled') : t('apiKeys.msg_toggle_disabled'));
      loadApiKeys();
    } catch {
      message.error(t('apiKeys.msg_toggle_failed'));
    }
  };

  const columns: ColumnsType<ApiKey> = [
    {
      title: t('apiKeys.col_name'),
      dataIndex: 'name',
      key: 'name',
      width: 180,
      ellipsis: true,
      render: (text: string) => (
        <Space>
          <KeyOutlined />
          <span>{text}</span>
        </Space>
      ),
    },
    {
      title: t('apiKeys.col_permissions'),
      dataIndex: 'permissions',
      key: 'permissions',
      width: 220,
      render: (permissions: Record<string, unknown>) => {
        if (!permissions || Object.keys(permissions).length === 0) return '-';
        return (
          <Space wrap>
            {Object.keys(permissions).map((p) => (
              <Tag key={p} color="blue">
                {p}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: t('apiKeys.col_call_count'),
      dataIndex: 'call_count',
      key: 'call_count',
      width: 100,
      sorter: (a, b) => a.call_count - b.call_count,
    },
    {
      title: t('apiKeys.col_key_display'),
      dataIndex: 'key_display',
      key: 'key_display',
      width: 160,
      render: (text: string) => <Input.Password value={text || '-'} readOnly variant="borderless" />,
    },
    {
      title: t('apiKeys.col_expires_at'),
      dataIndex: 'expires_at',
      key: 'expires_at',
      width: 160,
      render: (text: string | null) =>
        text ? dayjs(text).locale(getLocale()).format('YYYY-MM-DD HH:mm') : t('apiKeys.never_expires'),
    },
    {
      title: t('apiKeys.col_status'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (active: boolean, record: ApiKey) => (
        <Switch
          checked={active}
          checkedChildren={t('apiKeys.status_enabled')}
          unCheckedChildren={t('apiKeys.status_disabled')}
          size="small"
          onChange={(checked) => handleToggleActive(record, checked)}
        />
      ),
    },
    {
      title: t('apiKeys.col_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => dayjs(text).locale(getLocale()).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: t('apiKeys.col_actions'),
      key: 'actions',
      width: 160,
      fixed: 'right' as const,
      render: (_: unknown, record: ApiKey) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            {t('apiKeys.btn_edit')}
          </Button>
          <Popconfirm
            title={t('apiKeys.confirm_delete')}
            description={t('apiKeys.confirm_delete_desc', { name: record.name })}
            onConfirm={() => handleDelete(record)}
            okText={t('apiKeys.btn_delete')}
            cancelText={t('apiKeys.btn_cancel')}
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              {t('apiKeys.btn_delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper
      title={t('apiKeys.page_title')}
      extra={
        <Space>
          <Input.Search
            placeholder={t('apiKeys.search_placeholder')}
            allowClear
            className="gaf-w-200"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={() => {
              setPage(1);
              loadApiKeys();
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => loadApiKeys()}>
            {t('apiKeys.btn_refresh')}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            {t('apiKeys.btn_create')}
          </Button>
        </Space>
      }
    >
      <Card>
        <Table<ApiKey>
          rowKey="id"
          columns={columns}
          dataSource={apiKeys}
          loading={loading}
          scroll={{ x: 1200 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (total) => t('apiKeys.total_count', { count: total }),
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>

      <Modal
        title={isEdit ? t('apiKeys.modal_edit_title') : t('apiKeys.modal_create_title')}
        open={editorOpen}
        onOk={handleSubmit}
        onCancel={handleClose}
        confirmLoading={submitting}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" className="gaf-mt-lg">
          <Form.Item
            name="name"
            label={t('apiKeys.lbl_name')}
            rules={[{ required: true, message: t('apiKeys.msg_name_required') }]}
          >
            <Input placeholder={t('apiKeys.placeholder_name')} />
          </Form.Item>

          <Form.Item name="permissions" label={t('apiKeys.lbl_permissions')} tooltip={t('apiKeys.tooltip_permissions')}>
            <Select mode="tags" placeholder={t('apiKeys.placeholder_permissions')} className="gaf-w-full" />
          </Form.Item>

          <Form.Item
            name="ip_whitelist"
            label={t('apiKeys.lbl_ip_whitelist')}
            tooltip={t('apiKeys.tooltip_ip_whitelist')}
          >
            <Select mode="tags" placeholder={t('apiKeys.placeholder_ip')} className="gaf-w-full" />
          </Form.Item>

          <Form.Item name="expires_at" label={t('apiKeys.lbl_expires_at')}>
            <DatePicker
              showTime
              format="YYYY-MM-DD HH:mm"
              className="gaf-w-full"
              placeholder={t('apiKeys.placeholder_expires_at')}
            />
          </Form.Item>

          <Form.Item name="is_active" label={t('apiKeys.lbl_is_active')} valuePropName="checked">
            <Switch checkedChildren={t('apiKeys.status_enabled')} unCheckedChildren={t('apiKeys.status_disabled')} />
          </Form.Item>
        </Form>
      </Modal>
    </PageWrapper>
  );
}

export default ApiKeysPage;
