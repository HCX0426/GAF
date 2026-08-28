/**
 * Account Group Manager Drawer
 * Supports group CRUD, unassigned account drag-and-drop assignment, quick group creation
 */
import { useState, useEffect, useCallback } from 'react';
import { Drawer, Button, Input, Space, Tag, App, Popconfirm, Empty, Spin, theme } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import {
  fetchAccountGroups,
  createAccountGroup,
  updateAccountGroup,
  deleteAccountGroup,
  fetchGameAccounts,
  updateAccount,
} from '@/api/accounts';
import { useTranslation } from '@/i18n';
import type { AccountGroup, GameAccount } from '@/types/models';

interface AccountGroupManagerProps {
  open: boolean;
  onClose: () => void;
  onRefresh: () => void;
}

/** Preset group names */
const PRESET_GROUPS = ['Main', 'Alt', 'Farm', 'Event'];

/**
 * Account Group Manager component
 * Left side: group list; Right side: unassigned accounts with drag-drop support
 */
export function AccountGroupManager({ open, onClose, onRefresh }: AccountGroupManagerProps) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const t = useTranslation();
  const [groups, setGroups] = useState<AccountGroup[]>([]);
  const [unassignedAccounts, setUnassignedAccounts] = useState<GameAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingGroupId, setEditingGroupId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState('');
  const [creatingName, setCreatingName] = useState('');

  /** Load groups and unassigned accounts */
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // F9 fix (2026-08-28): 分离两个请求 — 之前 Promise.all + 空 catch 会因任一请求
      // 401/refresh 挂起导致整组永不渲染且无告警。
      let groupResults: AccountGroup[] = [];
      let unassigned: GameAccount[] = [];
      try {
        const groupRes = await fetchAccountGroups();
        groupResults = Array.isArray(groupRes) ? groupRes : groupRes.results ?? [];
      } catch (groupErr) {
        console.warn('[AccountGroupManager] fetch groups failed:', groupErr);
      }
      try {
        const accountRes = await fetchGameAccounts({ group: 'null', page_size: 200 });
        unassigned = Array.isArray(accountRes) ? accountRes : accountRes.results ?? [];
      } catch (accountErr) {
        console.warn('[AccountGroupManager] fetch unassigned accounts failed:', accountErr);
      }
      setGroups(groupResults);
      setUnassignedAccounts(unassigned);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadData();
    }
  }, [open, loadData]);

  /**
   * Create a new group
   */
  const handleCreate = async (name: string) => {
    if (!name.trim()) return;
    try {
      await createAccountGroup({ name: name.trim() });
      message.success(t('accounts.group_created', { name: name.trim() }));
      setCreatingName('');
      loadData();
    } catch {
      message.error(t('accounts.group_create_failed'));
    }
  };

  /**
   * Delete a group by ID
   */
  const handleDelete = async (id: number) => {
    try {
      await deleteAccountGroup(id);
      message.success(t('accounts.group_deleted'));
      loadData();
    } catch {
      message.error(t('accounts.group_delete_failed'));
    }
  };

  /**
   * Start editing a group name
   */
  const startEdit = (group: AccountGroup) => {
    setEditingGroupId(group.id);
    setEditingName(group.name);
  };

  /**
   * Save edited group name
   */
  const saveEdit = async () => {
    if (!editingName.trim() || editingGroupId === null) return;
    try {
      await updateAccountGroup(editingGroupId, { name: editingName.trim() });
      message.success(t('accounts.group_name_updated'));
      setEditingGroupId(null);
      loadData();
    } catch {
      message.error(t('accounts.group_update_failed'));
    }
  };

  /**
   * Handle account drag-and-drop onto a group
   */
  const handleDrop = async (groupId: number, e: React.DragEvent) => {
    const accountId = Number(e.dataTransfer.getData('accountId'));
    if (!accountId) return;

    try {
      await updateAccount(accountId, { group: groupId });
      message.success(t('accounts.account_moved'));

      loadData();
      onRefresh();
    } catch {
      message.error(t('accounts.account_move_failed'));
    }
  };

  return (
    <Drawer title={t('accounts.group_manager_title')} open={open} onClose={onClose} size={640}>
      <div className="gaf-flex gaf-gap-xl">
        {/* Left panel: group list */}
        <div className="gaf-flex-1">
          <h4>{t('accounts.group_list')}</h4>

          {/* Quick-create preset groups */}
          <div className="gaf-mb-md">
            <span className="gaf-mr-sm" style={{ color: token.colorTextTertiary }}>
              {t('accounts.quick_create')}
            </span>
            {PRESET_GROUPS.map((name) => (
              <Tag key={name} className="gaf-cursor-pointer" onClick={() => handleCreate(name)}>
                {name}
              </Tag>
            ))}
          </div>

          {/* Custom group creation */}
          <Space className="gaf-mb-lg gaf-w-full">
            <Input
              value={creatingName}
              onChange={(e) => setCreatingName(e.target.value)}
              placeholder={t('accounts.group_name_placeholder')}
              onPressEnter={() => {
                handleCreate(creatingName);
              }}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => handleCreate(creatingName)}>
              {t('accounts.create')}
            </Button>
          </Space>

          <Spin spinning={loading}>
            {groups.length === 0 ? (
              <Empty description={t('accounts.no_groups')} />
            ) : (
              <div>
                {groups.map((group) => (
                  <div
                    key={group.id}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => handleDrop(group.id, e)}
                    className="gaf-mb-sm gaf-py-sm gaf-px-md gaf-radius-md"
                    style={{ border: `1px dashed ${token.colorBorder}`, background: token.colorBgLayout }}
                  >
                    {editingGroupId === group.id ? (
                      <Input
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onPressEnter={saveEdit}
                        onBlur={saveEdit}
                        autoFocus
                        className="gaf-flex-1"
                      />
                    ) : (
                      <span className="gaf-flex-1 gaf-cursor-pointer" onDoubleClick={() => startEdit(group)}>
                        {group.name}
                        <Tag className="gaf-ml-sm">
                          {t('accounts.accounts_count', { count: group.account_count ?? 0 })}
                        </Tag>
                      </span>
                    )}
                    <Space>
                      <Button
                        type="link"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => startEdit(group)}
                        aria-label="编辑分组"
                      />
                      <Popconfirm title={t('accounts.confirm_delete_group')} onConfirm={() => handleDelete(group.id)}>
                        <Button type="link" size="small" danger icon={<DeleteOutlined />} aria-label="删除分组" />
                      </Popconfirm>
                    </Space>
                  </div>
                ))}
              </div>
            )}
          </Spin>
        </div>

        {/* Right panel: unassigned account list */}
        <div className="gaf-flex-1">
          <h4>{t('accounts.unassigned_accounts')}</h4>
          <Spin spinning={loading}>
            {unassignedAccounts.length === 0 ? (
              <Empty description={t('accounts.all_grouped')} />
            ) : (
              <div>
                {unassignedAccounts.map((account) => (
                  <div
                    key={account.id}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('accountId', String(account.id));
                    }}
                    className="gaf-mb-xs gaf-py-sm gaf-px-md gaf-radius-md"
                    style={{ border: `1px solid ${token.colorBorderSecondary}`, cursor: 'grab' }}
                  >
                    <span>{account.game_name}</span>
                    <span className="gaf-ml-sm" style={{ color: token.colorTextTertiary }}>
                      {account.username}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Spin>
        </div>
      </div>
    </Drawer>
  );
}

export default AccountGroupManager;
