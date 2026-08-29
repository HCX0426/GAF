/**
 * account rotation rules management Modal
 * supports create / edit / delete rotation rule, config sequential / random /
 * by_stamina / by_last_executed rotation strategy (aligned with backend
 * GameAccountRotationSerializer contract).
 */
import { useEffect, useState } from 'react';
import { Table, Button, Space, Modal, Form, Input, Select, Switch, InputNumber, App, Popconfirm, Tag } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { RotationRule, GameAccount } from '@/types/models';
import {
  fetchRotationRules,
  createRotationRule,
  updateRotationRule,
  deleteRotationRule,
  fetchGameAccounts,
} from '@/api/accounts';
import { useTranslation } from '@/i18n';

/** rotation strategy short label i18n key mapping */
const STRATEGY_SHORT_KEY: Record<string, string> = {
  sequential: 'accounts.strategy_sequential',
  random: 'accounts.strategy_random',
  by_stamina: 'accounts.strategy_by_stamina',
  by_last_executed: 'accounts.strategy_by_last_executed',
};

/** rotation strategy color mapping */
const STRATEGY_COLOR_MAP: Record<string, string> = {
  sequential: 'blue',
  random: 'green',
  by_stamina: 'orange',
  by_last_executed: 'purple',
};

interface AccountRotationRulesProps {
  open: boolean;
  onClose: () => void;
}

/**
 * rotation rule management component
 * show rule list and provides CRUD operation
 */
export function AccountRotationRules({ open, onClose }: AccountRotationRulesProps) {
  const { message } = App.useApp();
  const t = useTranslation();
  const [rules, setRules] = useState<RotationRule[]>([]);
  const [accounts, setAccounts] = useState<GameAccount[]>([]);
  const [form] = Form.useForm();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  /** form validation prompt info */
  const validateMessages = {
    required: t('accounts.field_required'),
  };

  /** rotation strategy option */
  const strategyOptions = [
    { label: t('accounts.strategy_sequential_label'), value: 'sequential' },
    { label: t('accounts.strategy_random_label'), value: 'random' },
    { label: t('accounts.strategy_by_stamina_label'), value: 'by_stamina' },
    { label: t('accounts.strategy_by_last_executed_label'), value: 'by_last_executed' },
  ];

  /** load rotation rule list */
  const loadRules = async () => {
    setLoading(true);
    try {
      const res = await fetchRotationRules();
      setRules(res.results || []);
    } catch {
      message.error(t('accounts.load_rules_failed'));
    } finally {
      setLoading(false);
    }
  };

  /** load game account options for the accounts multi-select */
  const loadAccounts = async () => {
    try {
      const res = await fetchGameAccounts({ page: 1, page_size: 200 });
      setAccounts(res.results || []);
    } catch {
      // silently ignore — the select will just have no options
    }
  };

  /** open page when load rule and account options */
  useEffect(() => {
    if (open) {
      loadRules();
      loadAccounts();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  /**
   * create new rule
   */
  const handleCreate = () => {
    form.resetFields();
    setEditingId(null);
    setModalOpen(true);
  };

  /**
   * edit existing rule
   */
  const handleEdit = (record: RotationRule) => {
    setEditingId(record.id);
    form.setFieldsValue({
      name: record.name,
      rotation_strategy: record.rotation_strategy,
      switch_interval_seconds: record.switch_interval_seconds,
      accounts: record.accounts,
      auto_skip_blocked: record.auto_skip_blocked,
    });
    setModalOpen(true);
  };

  /**
   * submit form ( create or update )
   */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        name: values.name,
        rotation_strategy: values.rotation_strategy,
        switch_interval_seconds: values.switch_interval_seconds,
        accounts: values.accounts,
        auto_skip_blocked: values.auto_skip_blocked ?? false,
      };
      if (editingId !== null) {
        await updateRotationRule(editingId, payload);
        message.success(t('accounts.rule_updated'));
      } else {
        await createRotationRule(payload);
        message.success(t('accounts.rule_created'));
      }
      setModalOpen(false);
      loadRules();
    } catch {
      // do not handle when form validation fails
    }
  };

  /**
   * delete rule ( with confirm )
   */
  const handleDelete = async (id: number) => {
    try {
      await deleteRotationRule(id);
      message.success(t('accounts.rule_deleted'));
      loadRules();
    } catch {
      message.error(t('accounts.rule_delete_failed'));
    }
  };

  /** account multi-select options (label = username + game name) */
  const accountOptions = accounts.map((acc) => ({
    value: acc.id,
    label: `${acc.username} (${acc.game_name_display})`,
  }));

  /** column definition */
  const columns = [
    {
      title: t('accounts.col_name'),
      dataIndex: 'name',
      key: 'name',
      width: 150,
    },
    {
      title: t('accounts.col_strategy'),
      dataIndex: 'rotation_strategy',
      key: 'rotation_strategy',
      width: 130,
      render: (val: string) => {
        const color = STRATEGY_COLOR_MAP[val];
        const labelKey = STRATEGY_SHORT_KEY[val];
        return labelKey ? <Tag color={color}>{t(labelKey)}</Tag> : val;
      },
    },
    {
      title: t('accounts.col_interval'),
      dataIndex: 'switch_interval_seconds',
      key: 'switch_interval_seconds',
      width: 100,
      align: 'center' as const,
      render: (val: number) => `${val ?? 0}`,
    },
    {
      title: t('accounts.col_accounts'),
      dataIndex: 'accounts',
      key: 'accounts',
      width: 90,
      align: 'center' as const,
      render: (val: number[]) => `${val?.length ?? 0}`,
    },
    {
      title: t('accounts.col_status'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 90,
      align: 'center' as const,
      render: (val: boolean) =>
        val ? <Tag color="success">{t('accounts.active')}</Tag> : <Tag>{t('accounts.inactive')}</Tag>,
    },
    {
      title: t('accounts.col_actions'),
      key: 'action',
      width: 120,
      render: (_: unknown, record: RotationRule) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
            aria-label="编辑规则"
          />
          <Popconfirm
            title={t('accounts.confirm_delete_rule')}
            onConfirm={() => handleDelete(record.id)}
            okText={t('accounts.confirm')}
            cancelText={t('accounts.cancel')}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />} aria-label="删除规则" />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Modal
      title={t('accounts.rotation_rules_title')}
      open={open}
      onCancel={onClose}
      footer={
        <Space>
          <Button onClick={onClose}>{t('accounts.close')}</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            {t('accounts.new_rule')}
          </Button>
        </Space>
      }
      width={800}
      destroyOnHidden
    >
      <Table
        dataSource={rules}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10 }}
        size="small"
        locale={{
          emptyText: t('accounts.no_rules'),
        }}
      />

      {/* 创建/编辑表单 */}
      <Modal
        title={editingId ? t('accounts.edit_rule') : t('accounts.new_rule')}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        destroyOnHidden
        width={520}
      >
        <Form
          form={form}
          layout="vertical"
          preserve={false}
          validateMessages={validateMessages}
          initialValues={{ rotation_strategy: 'sequential', switch_interval_seconds: 10, auto_skip_blocked: false }}
        >
          <Form.Item name="name" label={t('accounts.rule_name')} rules={[{ required: true }]}>
            <Input placeholder={t('accounts.rule_name_placeholder')} />
          </Form.Item>

          <Form.Item name="rotation_strategy" label={t('accounts.rotation_strategy')} rules={[{ required: true }]}>
            <Select options={strategyOptions} placeholder={t('accounts.select_strategy')} />
          </Form.Item>

          <Form.Item name="switch_interval_seconds" label={t('accounts.switch_interval')} rules={[{ required: true }]}>
            <Space.Compact className="gaf-w-full">
              <InputNumber
                min={1}
                style={{ width: '100%' }}
                placeholder={t('accounts.switch_interval_placeholder')}
              />
              <Input readOnly value={t('accounts.seconds_unit')} style={{ width: 48, textAlign: 'center' }} />
            </Space.Compact>
          </Form.Item>

          <Form.Item name="accounts" label={t('accounts.select_accounts')} rules={[{ required: true }]}>
            <Select
              mode="multiple"
              options={accountOptions}
              placeholder={t('accounts.select_accounts_placeholder')}
              optionFilterProp="label"
              showSearch
            />
          </Form.Item>

          <Form.Item name="auto_skip_blocked" label={t('accounts.auto_skip_blocked')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Modal>
  );
}

export default AccountRotationRules;
