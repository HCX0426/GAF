/**
 * user management page
 * system user CRUD: list, create, edit, delete, reset password, enable / disable
 * only admin can operation (API layer permission validate )
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
  Drawer,
  theme as antTheme,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  KeyOutlined,
  ReloadOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';

import { fetchUsers, createUser, updateUser, deleteUser, resetUserPassword } from '@/api/settings';
import { fetchLoginHistory } from '@/api/accounts';
import { useTranslation, getLocale } from '@/i18n';
import type { User, LoginHistory } from '@/types/models';
import PageWrapper from '@/components/Common/PageWrapper';

/** role Tag color mapping */
const ROLE_COLOR_MAP: Record<string, string> = {
  admin: 'red',
  operator: 'blue',
  viewer: 'default',
};

/** role i18n key mapping */
const ROLE_LABEL_KEY: Record<string, string> = {
  admin: 'accounts.role_admin',
  operator: 'accounts.role_operator',
  viewer: 'accounts.role_viewer',
};

export function UserManagePage() {
  const { message, modal } = App.useApp();
  const { token } = antTheme.useToken();
  const t = useTranslation();
  const locale = getLocale();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  // M4 Login History state
  const [historyUser, setHistoryUser] = useState<User | null>(null);
  const [historyData, setHistoryData] = useState<LoginHistory[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const isEdit = !!editingUser;

  /** edit mode below backfill form data, create new mode below reset */
  useEffect(() => {
    if (editorOpen && editingUser) {
      form.setFieldsValue({
        username: editingUser.username,
        role: editingUser.role,
        is_active: editingUser.is_active,
      });
    } else if (editorOpen) {
      form.resetFields();
    }
  }, [editorOpen, editingUser, form]);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchUsers({ page, page_size: pageSize });
      setUsers(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      message.error(t('accounts.load_users_failed'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, message, t]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleCreate = () => {
    setEditingUser(undefined);
    setEditorOpen(true);
  };

  const handleEdit = (record: User) => {
    setEditingUser(record);
    setEditorOpen(true);
  };

  const handleClose = () => {
    setEditorOpen(false);
  };

  const handleSubmit = async () => {
    try {
      const values = form.getFieldsValue();
      setSubmitting(true);

      if (isEdit) {
        await updateUser(Number(editingUser!.id), {
          username: editingUser!.username,
          role: values.role,
          is_active: values.is_active,
        });
        message.success(t('accounts.user_updated'));
      } else {
        await createUser({
          username: values.username,
          password: values.password,
          role: values.role,
        });
        message.success(t('accounts.user_created'));
      }

      setEditorOpen(false);
      loadUsers();
    } catch (err: unknown) {
      const error = err as { response?: { data?: Record<string, unknown> } };
      if (error.response?.data) {
        const details = Object.entries(error.response.data)
          .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(';') : v}`)
          .join(', ');
        message.error(details || t('accounts.operation_failed'));
      } else {
        message.error(t('accounts.operation_failed'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (user: User) => {
    try {
      await deleteUser(Number(user.id));
      message.success(t('accounts.user_deleted'));
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      const detail = error.response?.data?.detail;
      message.error(detail || t('accounts.delete_user_failed'));
    }
    loadUsers();
  };

  const handleResetPassword = async (user: User) => {
    try {
      const result = await resetUserPassword(Number(user.id));
      modal.success({
        title: t('accounts.password_reset'),
        content: (
          <div>
            <p>{t('accounts.new_password_prompt', { name: user.username })}</p>
            <Input.Password value={result.new_password} readOnly className="gaf-mt-sm" />
            <p className="gaf-mt-sm" style={{ color: token.colorTextTertiary }}>
              {t('accounts.password_delivery_note')}
            </p>
          </div>
        ),
      });
    } catch {
      message.error(t('accounts.reset_password_failed'));
    }
  };

  // M4: View login history for a specific user
  const handleViewHistory = useCallback(
    async (user: User) => {
      setHistoryUser(user);
      setHistoryLoading(true);
      try {
        const res = await fetchLoginHistory({
          user: user.id,
          page: 1,
          page_size: 50,
        });
        setHistoryData(res.results ?? []);
      } catch {
        message.error(t('accounts.load_history_failed'));
        setHistoryData([]);
      } finally {
        setHistoryLoading(false);
      }
    },
    [message, t],
  );

  const handleCloseHistory = useCallback(() => {
    setHistoryUser(null);
    setHistoryData([]);
  }, []);

  const historyColumns: ColumnsType<LoginHistory> = [
    {
      title: t('accounts.col_login_time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (val: string) => dayjs(val).locale(locale).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: t('accounts.col_ip'),
      dataIndex: 'ip_address',
      key: 'ip_address',
      width: 140,
    },
    {
      title: t('accounts.col_location'),
      dataIndex: 'location',
      key: 'location',
      width: 120,
      render: (val: string) => val || '-',
    },
    {
      title: t('accounts.col_user_agent'),
      dataIndex: 'user_agent',
      key: 'user_agent',
      ellipsis: true,
      render: (val: string) => (
        <span className="gaf-text-xs" style={{ color: token.colorTextTertiary }}>
          {val || '-'}
        </span>
      ),
    },
  ];

  const columns: ColumnsType<User> = [
    {
      title: t('accounts.username'),
      dataIndex: 'username',
      key: 'username',
      width: 160,
      ellipsis: true,
    },
    {
      title: t('accounts.col_role'),
      dataIndex: 'role',
      key: 'role',
      width: 100,
      render: (role: string) => (
        <Tag color={ROLE_COLOR_MAP[role] || 'default'}>{ROLE_LABEL_KEY[role] ? t(ROLE_LABEL_KEY[role]) : role}</Tag>
      ),
    },
    {
      title: t('accounts.col_user_status'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 80,
      render: (active: boolean) => (
        <Tag color={active ? 'green' : 'red'}>{active ? t('accounts.enabled') : t('accounts.disabled')}</Tag>
      ),
    },
    {
      title: t('accounts.col_must_change_password'),
      dataIndex: 'must_change_password',
      key: 'must_change_password',
      width: 120,
      render: (val: boolean) =>
        val ? <Tag color="orange">{t('accounts.required_label')}</Tag> : <Tag>{t('accounts.not_required')}</Tag>,
    },
    {
      title: t('accounts.col_last_login'),
      dataIndex: 'last_login',
      key: 'last_login',
      width: 160,
      render: (val: string | null) =>
        val ? dayjs(val).locale(locale).format('YYYY-MM-DD HH:mm') : t('accounts.never_login'),
    },
    {
      title: t('accounts.col_created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (val: string) => dayjs(val).locale(locale).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: t('accounts.col_actions'),
      key: 'actions',
      width: 280,
      render: (_: unknown, record: User) => (
        <Space size="small" wrap>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            {t('accounts.edit')}
          </Button>
          <Button type="link" size="small" icon={<KeyOutlined />} onClick={() => handleResetPassword(record)}>
            {t('accounts.reset_password')}
          </Button>
          <Button type="link" size="small" icon={<HistoryOutlined />} onClick={() => handleViewHistory(record)}>
            {t('accounts.login_history')}
          </Button>
          <Popconfirm
            title={t('accounts.confirm_delete_user')}
            description={t('accounts.delete_irreversible')}
            onConfirm={() => handleDelete(record)}
            okText={t('accounts.confirm')}
            cancelText={t('accounts.cancel')}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              {t('accounts.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper
      title={t('accounts.user_title')}
      extra={
        <Space wrap>
          <Button icon={<PlusOutlined />} type="primary" onClick={handleCreate}>
            {t('accounts.new_user')}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadUsers}>
            {t('accounts.refresh')}
          </Button>
        </Space>
      }
    >
      <Card>
        <Table
          columns={columns}
          dataSource={users}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (cnt) => t('accounts.total_users', { count: cnt }),
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>

      <Modal
        title={isEdit ? t('accounts.edit_user') : t('accounts.create_user')}
        open={editorOpen}
        onOk={handleSubmit}
        onCancel={handleClose}
        confirmLoading={submitting}
        destroyOnHidden
        width={480}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="username"
            label={t('accounts.username')}
            rules={isEdit ? [] : [{ required: true, message: t('accounts.username_required') }]}
          >
            <Input disabled={isEdit} placeholder={t('accounts.login_username_placeholder')} autoComplete="username" />
          </Form.Item>

          {!isEdit && (
            <Form.Item
              name="password"
              label={t('accounts.password')}
              rules={[
                { required: true, message: t('accounts.password_required') },
                { min: 6, message: t('accounts.password_min_length') },
              ]}
            >
              <Input.Password placeholder={t('accounts.password_placeholder')} autoComplete="new-password" />
            </Form.Item>
          )}

          <Form.Item
            name="role"
            label={t('accounts.col_role')}
            rules={[{ required: true, message: t('accounts.role_required') }]}
          >
            <Select
              options={[
                { label: t('accounts.role_admin_full'), value: 'admin' },
                { label: t('accounts.role_operator_full'), value: 'operator' },
                { label: t('accounts.role_viewer_full'), value: 'viewer' },
              ]}
            />
          </Form.Item>

          {isEdit && (
            <Form.Item name="is_active" label={t('accounts.enable_status')} valuePropName="checked">
              <Switch checkedChildren={t('accounts.enabled')} unCheckedChildren={t('accounts.disabled')} />
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* M4: Login History Drawer */}
      <Drawer
        title={t('accounts.history_title', { name: historyUser?.username ?? '' })}
        open={!!historyUser}
        onClose={handleCloseHistory}
        styles={{ wrapper: { width: 720 } }}
        destroyOnHidden
      >
        <Table
          columns={historyColumns}
          dataSource={historyData}
          rowKey="id"
          loading={historyLoading}
          size="small"
          pagination={{
            pageSize: 10,
            showSizeChanger: false,
            showTotal: (cnt) => t('accounts.total_records', { count: cnt }),
          }}
          locale={{ emptyText: t('accounts.no_login_records') }}
        />
      </Drawer>
    </PageWrapper>
  );
}

export default UserManagePage;
