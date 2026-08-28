/**
 * Device group panel.
 *
 * Provides quick filters (All / Ungrouped), a flat group list with inline
 * rename/delete actions, drag-and-drop assignment, and a polished empty state.
 */
import { useState } from 'react';
import { App, Button, Typography, Input, Space, Popconfirm, Tooltip, Badge, Empty, theme as antTheme } from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  FolderOutlined,
  CheckCircleOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { useDeviceStore } from '@/stores/useDeviceStore';
import type { DeviceGroup as DeviceGroupType } from '@/types/models';
import { useTranslation } from '@/i18n';

/** DeviceGroup component props */
interface DeviceGroupProps {
  onSelectGroup?: (groupId: number | null) => void;
  selectedGroupId?: number | null;
}

/**
 * Device group panel
 *
 * - Compact connected filter buttons (All / Ungrouped)
 * - Single, consistent create-row at the list top
 * - Flat group list with inline rename/delete
 * - Always-visible action buttons (no hover-only discovery)
 */
export function DeviceGroup({ onSelectGroup, selectedGroupId }: DeviceGroupProps) {
  const { groups, createGroup, updateGroup, deleteGroup } = useDeviceStore();
  const { message } = App.useApp();
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const [creating, setCreating] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');

  const isAllActive = selectedGroupId === null;
  const isUngroupedActive = selectedGroupId === -1;

  /** create new group */
  const handleCreate = async () => {
    const name = newGroupName.trim();
    if (!name) {
      message.warning(t('devices.group_name_required'));
      return;
    }
    try {
      await createGroup({ name });
      message.success(t('devices.group_create_success'));
      setNewGroupName('');
      setCreating(false);
    } catch {
      message.error(t('devices.group_create_failed'));
    }
  };

  /** save rename */
  const handleRename = async (id: number) => {
    const name = editName.trim();
    if (!name) {
      message.warning(t('devices.name_empty'));
      return;
    }
    try {
      await updateGroup(id, { name });
      message.success(t('devices.rename_success'));
      setEditingId(null);
    } catch {
      message.error(t('devices.rename_failed'));
    }
  };

  /** delete group */
  const handleDelete = async (id: number) => {
    try {
      await deleteGroup(id);
      message.success(t('devices.group_delete_success'));
      if (selectedGroupId === id && onSelectGroup) {
        onSelectGroup(null);
      }
    } catch {
      message.error(t('devices.group_delete_failed'));
    }
  };

  /** start edit group name */
  const startEdit = (group: DeviceGroupType) => {
    setEditingId(group.id);
    setEditName(group.name);
  };

  /** drag device to group */
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = async (e: React.DragEvent, groupId: number) => {
    e.preventDefault();
    const deviceId = e.dataTransfer.getData('text/plain');
    if (!deviceId) return;
    try {
      const group = groups.find((g) => g.id === groupId);
      if (!group) return;
      const deviceIds = new Set(group.devices);
      deviceIds.add(Number(deviceId));
      await updateGroup(groupId, { devices: Array.from(deviceIds) });
      message.success(t('devices.device_added_to_group'));
    } catch {
      message.error(t('devices.add_device_failed'));
    }
  };

  return (
    <div className="gaf-flex-col gaf-gap-sm device-group-panel">
      {/* Quick filters — single compact button bar */}
      <Space.Compact block size="small">
        <Button type={isAllActive ? 'primary' : 'default'} onClick={() => onSelectGroup?.(null)}>
          {t('devices.all')}
        </Button>
        <Button type={isUngroupedActive ? 'primary' : 'default'} onClick={() => onSelectGroup?.(-1)}>
          {t('devices.ungrouped')}
        </Button>
      </Space.Compact>

      {/* Group list */}
      <div
        className="gaf-flex-col device-group-list"
        style={{
          border: `1px solid ${token.colorBorderSecondary}`,
          borderRadius: token.borderRadiusLG,
          overflow: 'hidden',
          background: token.colorBgContainer,
        }}
      >
        {/* Header: create form when editing, otherwise a subtle add trigger */}
        {(groups.length > 0 || creating) && (
          <div
            className="gaf-flex-between gaf-gap-sm device-group-header"
            style={{
              padding: '6px 8px',
              borderBottom: `1px solid ${token.colorBorderSecondary}`,
              background: token.colorFillAlter,
            }}
          >
            {creating ? (
              <>
                <Input
                  size="small"
                  placeholder={t('devices.group_name_required')}
                  aria-label={t('devices.new_group_name')}
                  name="newGroupName"
                  autoComplete="off"
                  spellCheck={false}
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  onPressEnter={handleCreate}
                  className="gaf-flex-1"
                  autoFocus
                />
                <Space size={4}>
                  <Button
                    size="small"
                    type="text"
                    icon={<CheckCircleOutlined />}
                    aria-label={t('devices.confirm_create')}
                    onClick={handleCreate}
                  />
                  <Button
                    size="small"
                    type="text"
                    icon={<CloseOutlined />}
                    aria-label={t('devices.cancel_create')}
                    onClick={() => {
                      setCreating(false);
                      setNewGroupName('');
                    }}
                  />
                </Space>
              </>
            ) : (
              <>
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 500 }}>
                  {t('devices.add_group')}
                </Typography.Text>
                <Tooltip title={t('devices.add_group')}>
                  <Button
                    size="small"
                    type="text"
                    icon={<PlusOutlined />}
                    aria-label={t('devices.add_group')}
                    onClick={() => setCreating(true)}
                  />
                </Tooltip>
              </>
            )}
          </div>
        )}

        {!creating && groups.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('devices.no_groups')}
              </Typography.Text>
            }
            style={{ padding: '16px 4px' }}
          >
            <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setCreating(true)} block>
              {t('devices.add_group')}
            </Button>
          </Empty>
        ) : (
          groups.map((group) => {
            const isSelected = selectedGroupId === group.id;
            return (
              <div
                key={group.id}
                role="button"
                tabIndex={0}
                aria-label={`${t('devices.select_group')} ${group.name}`}
                aria-current={isSelected ? 'true' : undefined}
                className="gaf-flex-between gaf-gap-sm group-row"
                onClick={() => onSelectGroup?.(group.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectGroup?.(group.id);
                  }
                }}
                onDragOver={handleDragOver}
                onDrop={(e) => handleDrop(e, group.id)}
                style={{
                  padding: '8px 10px',
                  cursor: 'pointer',
                  background: isSelected ? token.colorPrimaryBg : 'transparent',
                  borderLeft: isSelected ? `3px solid ${token.colorPrimary}` : '3px solid transparent',
                }}
              >
                {editingId === group.id ? (
                  <Space className="gaf-w-full" size={4}>
                    <Input
                      size="small"
                      value={editName}
                      aria-label={t('devices.new_group_name')}
                      name="groupName"
                      autoComplete="off"
                      spellCheck={false}
                      onChange={(e) => setEditName(e.target.value)}
                      onPressEnter={() => handleRename(group.id)}
                      className="gaf-flex-1"
                      onClick={(e) => e.stopPropagation()}
                      autoFocus
                    />
                    <Button
                      size="small"
                      type="text"
                      icon={<CheckCircleOutlined />}
                      aria-label={t('devices.confirm_rename')}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRename(group.id);
                      }}
                    />
                    <Button
                      size="small"
                      type="text"
                      icon={<CloseOutlined />}
                      aria-label={t('devices.cancel_rename')}
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingId(null);
                      }}
                    />
                  </Space>
                ) : (
                  <>
                    <Space size={6} className="gaf-flex-1" style={{ overflow: 'hidden' }}>
                      <FolderOutlined style={{ color: token.colorPrimary, fontSize: 14 }} aria-hidden="true" />
                      <Typography.Text
                        ellipsis
                        style={{
                          maxWidth: 120,
                          color: isSelected ? token.colorPrimaryText : token.colorText,
                          fontWeight: isSelected ? 500 : 400,
                        }}
                      >
                        {group.name}
                      </Typography.Text>
                    </Space>
                    <Space size={0} className="group-actions">
                      <Badge
                        count={group.device_count}
                        size="small"
                        style={{
                          backgroundColor: isSelected ? token.colorPrimary : token.colorTextDisabled,
                        }}
                      />
                      <Tooltip title={t('devices.rename')}>
                        <Button
                          size="small"
                          type="text"
                          icon={<EditOutlined />}
                          aria-label={t('devices.rename')}
                          onClick={(e) => {
                            e.stopPropagation();
                            startEdit(group);
                          }}
                        />
                      </Tooltip>
                      <Popconfirm
                        title={t('devices.delete_group_confirm')}
                        onConfirm={(e) => {
                          e?.stopPropagation();
                          handleDelete(group.id);
                        }}
                        onCancel={(e) => e?.stopPropagation()}
                        okText={t('devices.delete')}
                        cancelText={t('devices.cancel_create')}
                      >
                        <Tooltip title={t('devices.delete')}>
                          <Button
                            size="small"
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            aria-label={t('devices.delete')}
                            onClick={(e) => e.stopPropagation()}
                          />
                        </Tooltip>
                      </Popconfirm>
                    </Space>
                  </>
                )}
              </div>
            );
          })
        )}
      </div>

      <style>{`
        .group-row {
          transition: background-color 0.2s ease;
        }
        .group-row:hover {
          background-color: ${token.colorFillTertiary} !important;
        }
        .group-row:focus-visible {
          outline: 2px solid ${token.colorPrimary};
          outline-offset: -2px;
          position: relative;
          z-index: 1;
        }
        .group-actions .ant-btn {
          opacity: 0.75;
          transition: opacity 0.2s ease, color 0.2s ease;
        }
        .group-row:hover .group-actions .ant-btn,
        .group-actions .ant-btn:focus-visible {
          opacity: 1;
        }
      `}</style>
    </div>
  );
}

export default DeviceGroup;
