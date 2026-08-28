/**
 * game account management main page
 * integrates account list, search filter, batch operations and has child feature Modal/Drawer
 */
import { useEffect, useState, useCallback } from 'react';
import { Table, Button, Space, Input, Select, Tag, Badge, Popconfirm, App, Card } from 'antd';
import {
  PlusOutlined,
  ImportOutlined,
  CheckCircleOutlined,
  EditOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  GroupOutlined,
  SyncOutlined,
  SettingOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';

import { fetchGameAccounts, deleteAccount } from '@/api/accounts';
import { useTranslation, getLocale } from '@/i18n';
import type { GameAccount } from '@/types/models';
import PageWrapper from '@/components/Common/PageWrapper';
import GameAccountEditor from './GameAccountEditor';
import AccountLoginTester from './components/AccountLoginTester';
import AccountBatchChecker from './components/AccountBatchChecker';
import AccountGroupManager from './components/AccountGroupManager';
import AccountRotationRules from './components/AccountRotationRules';
import AccountStatusPanel from './components/AccountStatusPanel';
import AccountAutoHandler from './components/AccountAutoHandler';
import AccountBatchImport from './components/AccountBatchImport';

dayjs.extend(relativeTime);
/** status Badge mapping */
const STATUS_BADGE_MAP: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  ok: 'success',
  warn: 'warning',
  error: 'error',
  unknown: 'default',
};

/** status i18n key mapping */
const STATUS_TEXT_KEY: Record<string, string> = {
  ok: 'accounts.status_ok',
  warn: 'accounts.status_warn',
  error: 'accounts.status_error',
  unknown: 'accounts.status_unknown',
};

/** login method i18n key mapping */
const LOGIN_METHOD_KEY: Record<string, string> = {
  password: 'accounts.login_method_password',
  qr_scan: 'accounts.login_method_qr_scan',
  token: 'accounts.login_method_token',
  steam: 'accounts.login_method_steam',
};

/** game account management main page */
export function GameAccountsPage() {
  const { message, modal } = App.useApp();
  const t = useTranslation();
  const locale = getLocale();
  const [accounts, setAccounts] = useState<GameAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [groupFilter, setGroupFilter] = useState<number | undefined>(undefined);
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);

  /** Editor Modal status */
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<GameAccount | undefined>(undefined);

  /** child feature Modal/Drawer status */
  const [loginTesterOpen, setLoginTesterOpen] = useState(false);
  const [loginTestAccount, setLoginTestAccount] = useState<{ id: number; name: string }>({ id: 0, name: '' });
  const [batchCheckerOpen, setBatchCheckerOpen] = useState(false);
  const [groupManagerOpen, setGroupManagerOpen] = useState(false);
  const [rotationRulesOpen, setRotationRulesOpen] = useState(false);
  const [statusPanelOpen, setStatusPanelOpen] = useState(false);
  const [statusPanelAccount, setStatusPanelAccount] = useState<GameAccount | undefined>(undefined);
  const [batchImportOpen, setBatchImportOpen] = useState(false);

  /**
   * load account list
   */
  const loadAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        page,
        page_size: pageSize,
      };
      if (search) params.search = search;
      if (statusFilter) params.status = statusFilter;
      if (groupFilter) params.group = groupFilter;

      const res = await fetchGameAccounts(params);
      setAccounts(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      message.error(t('accounts.load_failed'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, statusFilter, groupFilter, message, t]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  /**
   * create new account
   */
  const handleCreate = () => {
    setEditingAccount(undefined);
    setEditorOpen(true);
  };

  /**
   * edit account
   */
  const handleEdit = (record: GameAccount) => {
    setEditingAccount(record);
    setEditorOpen(true);
  };

  /**
   * row click open status panel
   */
  const handleRowClick = (record: GameAccount) => {
    setStatusPanelAccount(record);
    setStatusPanelOpen(true);
  };

  /**
   * delete account
   */
  const handleDelete = async (id: number) => {
    try {
      await deleteAccount(id);
      message.success(t('accounts.deleted'));
      loadAccounts();
    } catch {
      message.error(t('accounts.delete_failed'));
    }
  };

  /**
   * test login
   */
  const handleTestLogin = (record: GameAccount) => {
    setLoginTestAccount({ id: record.id, name: `${record.game_name} - ${record.username}` });
    setLoginTesterOpen(true);
  };

  /**
   * Editor success callback
   */
  const handleEditorSuccess = () => {
    setEditorOpen(false);
    loadAccounts();
  };

  /**
   * batch detect complete callback
   */
  const handleBatchCheckComplete = () => {
    loadAccounts();
  };

  /**
   * batch import complete callback
   */
  const handleImportComplete = () => {
    loadAccounts();
  };

  /** table column definition */
  const columns: ColumnsType<GameAccount> = [
    {
      title: t('accounts.col_game_name'),
      dataIndex: 'game_name',
      key: 'game_name',
      width: 120,
    },
    {
      title: t('accounts.col_username'),
      dataIndex: 'username',
      key: 'username',
      width: 140,
      ellipsis: true,
    },
    {
      title: t('accounts.col_server_region'),
      dataIndex: 'server_region',
      key: 'server_region',
      width: 120,
      ellipsis: true,
      render: (val: string) => val || '-',
    },
    {
      title: t('accounts.col_login_method'),
      dataIndex: 'login_method',
      key: 'login_method',
      width: 100,
      render: (method: string) => <Tag>{LOGIN_METHOD_KEY[method] ? t(LOGIN_METHOD_KEY[method]) : method}</Tag>,
    },
    {
      title: t('accounts.col_status'),
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => (
        <Badge
          status={STATUS_BADGE_MAP[status] || 'default'}
          text={STATUS_TEXT_KEY[status] ? t(STATUS_TEXT_KEY[status]) : status}
        />
      ),
    },
    {
      title: t('accounts.col_group'),
      dataIndex: 'group_name',
      key: 'group_name',
      width: 100,
      render: (name: string | null) => (name ? <Tag color="blue">{name}</Tag> : <Tag>{t('accounts.ungrouped')}</Tag>),
    },
    {
      title: t('accounts.col_last_login'),
      dataIndex: 'last_login_at',
      key: 'last_login_at',
      width: 130,
      render: (val: string | null) => (val ? dayjs(val).locale(locale).fromNow() : t('accounts.never_login')),
    },
    {
      title: t('accounts.col_login_count'),
      dataIndex: 'login_count',
      key: 'login_count',
      width: 90,
      align: 'center',
    },
    {
      title: t('accounts.col_execution_count'),
      dataIndex: 'execution_count',
      key: 'execution_count',
      width: 90,
      align: 'center',
    },
    {
      title: t('accounts.col_actions'),
      key: 'actions',
      width: 260,
      render: (_: unknown, record: GameAccount) => (
        <Space size="small" wrap>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              handleEdit(record);
            }}
          >
            {t('accounts.edit')}
          </Button>
          <Popconfirm
            title={t('accounts.confirm_delete')}
            description={t('accounts.delete_irreversible')}
            onConfirm={(e) => {
              e?.stopPropagation();
              handleDelete(record.id);
            }}
            onCancel={(e) => e?.stopPropagation()}
            okText={t('accounts.confirm')}
            cancelText={t('accounts.cancel')}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()}>
              {t('accounts.delete')}
            </Button>
          </Popconfirm>
          <Button
            type="link"
            size="small"
            icon={<ExperimentOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              handleTestLogin(record);
            }}
          >
            {t('accounts.test')}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper title={t('accounts.title')}>
      <Card>
        {/* 操作工具栏 */}
        <div className="gaf-toolbar gaf-mb-lg">
          <Button icon={<PlusOutlined />} type="primary" onClick={handleCreate}>
            {t('accounts.new_account')}
          </Button>
          <Button icon={<ImportOutlined />} onClick={() => setBatchImportOpen(true)}>
            {t('accounts.batch_import')}
          </Button>
          <Button
            icon={<CheckCircleOutlined />}
            onClick={() => setBatchCheckerOpen(true)}
            disabled={selectedRowKeys.length === 0}
          >
            {t('accounts.batch_check')}
          </Button>
          <Button icon={<GroupOutlined />} onClick={() => setGroupManagerOpen(true)}>
            {t('accounts.group_management')}
          </Button>
          <Button icon={<SyncOutlined />} onClick={() => setRotationRulesOpen(true)}>
            {t('accounts.rotation_rules')}
          </Button>
          <Button
            icon={<SettingOutlined />}
            onClick={() => {
              modal.info({
                title: t('accounts.exception_handler_title'),
                content: <AccountAutoHandler />,
                footer: null,
              });
            }}
          >
            {t('accounts.exception_handler')}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadAccounts}>
            {t('accounts.refresh')}
          </Button>
        </div>

        {/* 搜索与筛选 */}
        <div className="gaf-toolbar gaf-gap-md gaf-mb-lg">
          <Input.Search
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onSearch={() => {
              setPage(1);
              loadAccounts();
            }}
            placeholder={t('accounts.search_placeholder')}
            style={{ width: 280 }}
            allowClear
            aria-label={t('accounts.search_placeholder')}
            name="account_search"
            autoComplete="off"
          />
          <Select
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v);
              setPage(1);
            }}
            placeholder={t('accounts.status_filter')}
            style={{ width: 140 }}
            allowClear
            options={[
              { label: t('accounts.status_ok'), value: 'ok' },
              { label: t('accounts.status_warn'), value: 'warn' },
              { label: t('accounts.status_error'), value: 'error' },
              { label: t('accounts.status_unknown'), value: 'unknown' },
            ]}
          />
          <Select
            value={groupFilter}
            onChange={(v) => {
              setGroupFilter(v);
              setPage(1);
            }}
            placeholder={t('accounts.group_filter')}
            style={{ width: 140 }}
            allowClear
          />
        </div>

        {/* 数据表格 */}
        <Table
          columns={columns}
          dataSource={accounts}
          rowKey="id"
          loading={loading}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as number[]),
          }}
          onRow={(record) => ({
            onClick: () => handleRowClick(record),
            style: { cursor: 'pointer' },
          })}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (cnt) => t('accounts.total_accounts', { count: cnt }),
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
        />
      </Card>

      {/* 创建/编辑 Modal */}
      <GameAccountEditor
        open={editorOpen}
        account={editingAccount}
        onClose={() => setEditorOpen(false)}
        onSuccess={handleEditorSuccess}
      />

      {/* 登录测试 Modal */}
      <AccountLoginTester
        accountId={loginTestAccount.id}
        accountName={loginTestAccount.name}
        open={loginTesterOpen}
        onClose={() => setLoginTesterOpen(false)}
      />

      {/* 批量检测 Modal */}
      <AccountBatchChecker
        accountIds={selectedRowKeys}
        open={batchCheckerOpen}
        onClose={() => setBatchCheckerOpen(false)}
        onComplete={handleBatchCheckComplete}
      />

      {/* 分组管理 Drawer */}
      <AccountGroupManager
        open={groupManagerOpen}
        onClose={() => setGroupManagerOpen(false)}
        onRefresh={loadAccounts}
      />

      {/* 轮换规则 Modal */}
      <AccountRotationRules open={rotationRulesOpen} onClose={() => setRotationRulesOpen(false)} />

      {/* 状态面板 Drawer */}
      {statusPanelAccount && (
        <AccountStatusPanel
          account={statusPanelAccount}
          open={statusPanelOpen}
          onClose={() => setStatusPanelOpen(false)}
        />
      )}

      {/* 批量导入 Modal */}
      <AccountBatchImport
        open={batchImportOpen}
        onClose={() => setBatchImportOpen(false)}
        onComplete={handleImportComplete}
      />
    </PageWrapper>
  );
}

export default GameAccountsPage;
