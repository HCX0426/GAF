/**
 * Feature Flag management page
 * CRUD for feature flags: name, description, enabled status,
 * rollout percentage, role whitelist, IP whitelist
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
  App,
  InputNumber,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, FlagOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchFeatureFlags, createFeatureFlag, updateFeatureFlag, deleteFeatureFlag } from '@/api/tasks';
import type { FeatureFlag } from '@/types/models';
import { useTranslation } from '@/i18n';
import PageWrapper from '@/components/Common/PageWrapper';

const { TextArea } = Input;

export function FeatureFlagsPage() {
  const { message } = App.useApp();
  const t = useTranslation();
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [searchText, setSearchText] = useState('');

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingFlag, setEditingFlag] = useState<FeatureFlag | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const isEdit = !!editingFlag;

  /** Fill form data when editing, reset when creating */
  useEffect(() => {
    if (editorOpen && editingFlag) {
      form.setFieldsValue({
        name: editingFlag.name,
        description: editingFlag.description,
        enabled: editingFlag.enabled,
        rollout_percentage: editingFlag.rollout_percentage,
        allowed_roles: editingFlag.allowed_roles || [],
        allowed_ips: editingFlag.allowed_ips || [],
      });
    } else if (editorOpen) {
      form.resetFields();
      form.setFieldsValue({
        enabled: true,
        rollout_percentage: 100,
      });
    }
  }, [editorOpen, editingFlag, form]);

  const loadFlags = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchFeatureFlags({
        page,
        page_size: pageSize,
        search: searchText || undefined,
      });
      setFlags(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      message.error(t('featureFlags.msg_load_failed'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchText, message, t]);

  useEffect(() => {
    loadFlags();
  }, [loadFlags]);

  const handleCreate = () => {
    setEditingFlag(undefined);
    setEditorOpen(true);
  };

  const handleEdit = (record: FeatureFlag) => {
    setEditingFlag(record);
    setEditorOpen(true);
  };

  const handleClose = () => {
    setEditorOpen(false);
    setEditingFlag(undefined);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      const data = {
        name: values.name,
        description: values.description || '',
        enabled: values.enabled,
        rollout_percentage: values.rollout_percentage ?? 100,
        allowed_roles: values.allowed_roles || [],
        allowed_ips: values.allowed_ips || [],
      };

      setSubmitting(true);

      if (isEdit) {
        await updateFeatureFlag(editingFlag!.id, data);
        message.success(t('featureFlags.msg_updated'));
      } else {
        await createFeatureFlag(data);
        message.success(t('featureFlags.msg_created'));
      }

      setEditorOpen(false);
      loadFlags();
    } catch {
      message.error(isEdit ? t('featureFlags.msg_update_failed') : t('featureFlags.msg_create_failed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (record: FeatureFlag) => {
    try {
      await deleteFeatureFlag(record.id);
      message.success(t('featureFlags.msg_deleted'));
      loadFlags();
    } catch {
      message.error(t('featureFlags.msg_delete_failed'));
    }
  };

  const handleToggleEnabled = async (record: FeatureFlag, checked: boolean) => {
    try {
      await updateFeatureFlag(record.id, { ...record, enabled: checked });
      message.success(checked ? t('featureFlags.msg_enabled') : t('featureFlags.msg_disabled'));
      loadFlags();
    } catch {
      message.error(t('featureFlags.msg_toggle_failed'));
    }
  };

  const columns: ColumnsType<FeatureFlag> = [
    {
      title: t('featureFlags.col_name'),
      dataIndex: 'name',
      key: 'name',
      width: 160,
      ellipsis: true,
      render: (text: string) => (
        <Space>
          <FlagOutlined />
          <span>{text}</span>
        </Space>
      ),
    },
    {
      title: t('featureFlags.col_description'),
      dataIndex: 'description',
      key: 'description',
      width: 200,
      ellipsis: true,
      render: (text: string) => text || '-',
    },
    {
      title: t('featureFlags.col_status'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record: FeatureFlag) => (
        <Switch
          checked={enabled}
          checkedChildren={t('featureFlags.switch_enable')}
          unCheckedChildren={t('featureFlags.switch_disable')}
          size="small"
          onChange={(checked) => handleToggleEnabled(record, checked)}
        />
      ),
    },
    {
      title: t('featureFlags.col_rollout'),
      dataIndex: 'rollout_percentage',
      key: 'rollout_percentage',
      width: 120,
      render: (pct: number) => <Tag color={pct === 100 ? 'green' : pct === 0 ? 'red' : 'orange'}>{pct}%</Tag>,
    },
    {
      title: t('featureFlags.col_roles'),
      dataIndex: 'allowed_roles',
      key: 'allowed_roles',
      width: 180,
      render: (roles: string[]) => {
        if (!roles || roles.length === 0) return <Tag>{t('featureFlags.tag_all')}</Tag>;
        return (
          <Space wrap>
            {roles.map((r) => (
              <Tag key={r} color="blue">
                {r}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: t('featureFlags.col_ips'),
      dataIndex: 'allowed_ips',
      key: 'allowed_ips',
      width: 180,
      ellipsis: true,
      render: (ips: string[]) => {
        if (!ips || ips.length === 0) return <Tag>{t('featureFlags.tag_all')}</Tag>;
        return (
          <Space wrap>
            {ips.slice(0, 2).map((ip) => (
              <Tag key={ip}>{ip}</Tag>
            ))}
            {ips.length > 2 && <Tag>+{ips.length - 2}</Tag>}
          </Space>
        );
      },
    },
    {
      title: t('featureFlags.col_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => dayjs(text).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: t('featureFlags.col_actions'),
      key: 'actions',
      width: 160,
      fixed: 'right' as const,
      render: (_: unknown, record: FeatureFlag) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            {t('featureFlags.btn_edit')}
          </Button>
          <Popconfirm
            title={t('featureFlags.confirm_delete_title')}
            description={t('featureFlags.confirm_delete_desc', { name: record.name })}
            onConfirm={() => handleDelete(record)}
            okText={t('featureFlags.confirm_ok')}
            cancelText={t('featureFlags.confirm_cancel')}
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              {t('featureFlags.btn_delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper
      title={t('featureFlags.page_title')}
      extra={
        <Space>
          <Input.Search
            placeholder={t('featureFlags.search_placeholder')}
            allowClear
            className="gaf-w-200"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={() => {
              setPage(1);
              loadFlags();
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => loadFlags()}>
            {t('featureFlags.btn_refresh')}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            {t('featureFlags.btn_create')}
          </Button>
        </Space>
      }
    >
      <Card>
        <Table<FeatureFlag>
          rowKey="id"
          columns={columns}
          dataSource={flags}
          loading={loading}
          scroll={{ x: 1200 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (total) => t('featureFlags.total_label', { total }),
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>

      <Modal
        title={isEdit ? t('featureFlags.modal_title_edit') : t('featureFlags.modal_title_create')}
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
            label={t('featureFlags.label_name')}
            rules={[{ required: true, message: t('featureFlags.validate_name_required') }]}
          >
            <Input placeholder={t('featureFlags.placeholder_name')} />
          </Form.Item>

          <Form.Item name="description" label={t('featureFlags.label_description')}>
            <TextArea rows={3} placeholder={t('featureFlags.placeholder_description')} />
          </Form.Item>

          <Form.Item name="enabled" label={t('featureFlags.label_enabled')} valuePropName="checked">
            <Switch
              checkedChildren={t('featureFlags.switch_enable')}
              unCheckedChildren={t('featureFlags.switch_disable')}
            />
          </Form.Item>

          <Form.Item
            name="rollout_percentage"
            label={t('featureFlags.label_rollout')}
            rules={[{ required: true, message: t('featureFlags.validate_rollout_required') }]}
          >
            <Space.Compact className="gaf-w-full">
              <InputNumber min={0} max={100} className="gaf-w-full" placeholder="0-100" />
              <Input readOnly value="%" style={{ width: 48, textAlign: 'center' }} />
            </Space.Compact>
          </Form.Item>

          <Form.Item
            name="allowed_roles"
            label={t('featureFlags.label_roles')}
            tooltip={t('featureFlags.tooltip_roles')}
          >
            <Select mode="tags" placeholder={t('featureFlags.placeholder_roles')} className="gaf-w-full" />
          </Form.Item>

          <Form.Item name="allowed_ips" label={t('featureFlags.label_ips')} tooltip={t('featureFlags.tooltip_ips')}>
            <Select mode="tags" placeholder={t('featureFlags.placeholder_ips')} className="gaf-w-full" />
          </Form.Item>
        </Form>
      </Modal>
    </PageWrapper>
  );
}

export default FeatureFlagsPage;
