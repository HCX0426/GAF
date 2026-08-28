/**
 * group manager component ( tree-shaped drag?
 * supports group tree show, create rename? delete group, device drag to group
 */
import { useState, useMemo, useCallback } from 'react';
import { Tree, Button, Input, Dropdown, Badge, App, theme as antTheme } from 'antd';
import type { MenuProps } from 'antd';
import { FolderOutlined, PlusOutlined } from '@ant-design/icons';
import { useDeviceStore } from '@/stores/useDeviceStore';
import type { DeviceGroup } from '@/types/models';
import { useTranslation } from '@/i18n';

/** DeviceGroupManager component property?*/
interface DeviceGroupManagerProps {
  selectedGroupId: number | null;
  onSelectGroup: (groupId: number | null) => void;
  onDeviceDrop?: (deviceId: number, groupId: number) => void;
}

/** Tree node data type */
interface TreeNodeData {
  key: string;
  title: React.ReactNode;
  children?: TreeNodeData[];
  isLeaf?: boolean;
  groupId?: number;
  deviceCount?: number;
}

/**
 * group management?
 * left: tree group list, supports create, rename, delete groups, and device drag assignment
 */
export function DeviceGroupManager({ selectedGroupId, onSelectGroup, onDeviceDrop }: DeviceGroupManagerProps) {
  const { message, modal } = App.useApp();
  const { token } = antTheme.useToken();
  const { groups, createGroup, updateGroup, deleteGroup } = useDeviceStore();
  const t = useTranslation();
  const [creating, setCreating] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [editingNodeKey, setEditingNodeKey] = useState<string | null>(null);
  const [editName, setEditName] = useState('');

  /**?DeviceGroup recursive convert?Tree node data */
  const toTreeNode = (group: DeviceGroup): TreeNodeData => ({
    key: `group-${group.id}`,
    title: group.name,
    groupId: group.id,
    deviceCount: group.device_count,
    children: group.children?.map((child) =>
      toTreeNode({
        ...child,
        devices: [],
        devices_detail: [],
        user: 0,
        created_at: '',
        updated_at: '',
      } as unknown as DeviceGroup),
    ),
  });

  /** build complete tree data: all device + ungrouped?+ group list */
  const treeData = useMemo<TreeNodeData[]>(() => {
    const nodes: TreeNodeData[] = [
      {
        key: 'all',
        title: '全部设备',
        isLeaf: true,
        children: [],
      },
      {
        key: 'ungrouped',
        title: '未分组',
        isLeaf: true,
        deviceCount: 0,
        children: [],
      },
      ...(groups || []).map(toTreeNode),
    ];
    return nodes;
  }, [groups]);

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

  /** save rename?*/
  const handleRename = async () => {
    if (!editingNodeKey || !editingNodeKey.startsWith('group-')) return;
    const name = editName.trim();
    if (!name) {
      message.warning(t('devices.name_empty'));
      return;
    }
    const groupId = Number(editingNodeKey.replace('group-', ''));
    try {
      await updateGroup(groupId, { name });
      message.success(t('devices.rename_success'));
      setEditingNodeKey(null);
    } catch {
      message.error(t('devices.rename_failed'));
    }
  };

  /** delete group */
  const handleDelete = (nodeKey: string) => {
    if (!nodeKey.startsWith('group-')) return;
    const groupId = Number(nodeKey.replace('group-', ''));
    modal.confirm({
      title: '删除分组',
      content: '确定要删除此分组吗？分组内的设备将移至未分组',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteGroup(groupId);
          message.success(t('devices.group_delete_success'));
          if (selectedGroupId === groupId) {
            onSelectGroup(null);
          }
        } catch {
          message.error(t('devices.group_delete_failed'));
        }
      },
    });
  };

  /** right key menu?*/
  const getContextMenuItems = (nodeKey: string): MenuProps['items'] => {
    if (nodeKey === 'all' || nodeKey === 'ungrouped') return [];
    return [
      {
        key: 'rename',
        label: '重命名',
        onClick: () => {
          const group = groups.find((g) => `group-${g.id}` === nodeKey);
          if (group) {
            setEditingNodeKey(nodeKey);
            setEditName(group.name);
          }
        },
      },
      {
        key: 'delete',
        label: '删除',
        danger: true,
        onClick: () => handleDelete(nodeKey),
      },
    ];
  };

  /** custom node title render */
  const titleRender = useCallback(
    (nodeData: TreeNodeData) => {
      if (editingNodeKey === nodeData.key) {
        return (
          <Input
            size="small"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onPressEnter={handleRename}
            onBlur={() => setEditingNodeKey(null)}
            autoFocus
            style={{ width: 140 }}
            onClick={(e) => e.stopPropagation()}
          />
        );
      }

      const menuItems = getContextMenuItems(nodeData.key);
      const inner = (
        <span
          className="gaf-inline-flex"
          style={{ alignItems: 'center', gap: 6 }}
          onDragOver={(e) => {
            if (nodeData.key === 'all') return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
          }}
          onDrop={(e) => {
            if (nodeData.key === 'all' || nodeData.key === 'ungrouped') return;
            e.preventDefault();
            const deviceIdStr = e.dataTransfer.getData('text/plain');
            if (!deviceIdStr || !onDeviceDrop) return;
            const deviceId = Number(deviceIdStr);
            if (Number.isNaN(deviceId)) return;
            const targetGroupId = nodeData.groupId ?? Number(nodeData.key.replace('group-', ''));
            onDeviceDrop(deviceId, targetGroupId);
          }}
        >
          <FolderOutlined style={{ color: token.colorPrimary }} />
          <span>{nodeData.title as string}</span>
          {nodeData.deviceCount != null && nodeData.deviceCount > 0 && (
            <Badge count={nodeData.deviceCount} size="small" style={{ backgroundColor: token.colorPrimary }} />
          )}
        </span>
      );

      if (menuItems!.length === 0) {
        return inner;
      }

      return (
        <Dropdown menu={{ items: menuItems }} trigger={['contextMenu']}>
          {inner}
        </Dropdown>
      );
    },
    [editingNodeKey, editName, groups, onDeviceDrop],
  );

  /** tree node select in handle */
  const handleSelect = (_selectedKeys: React.Key[], info: { node: TreeNodeData }) => {
    const { node } = info;
    if (node.key === 'all') {
      onSelectGroup(null);
    } else if (node.key === 'ungrouped') {
      onSelectGroup(-1);
    } else if (node.groupId != null) {
      onSelectGroup(node.groupId);
    }
  };

  /** confirm current select in?key */
  const selectedKeys = useMemo(() => {
    if (selectedGroupId === null) return ['all'];
    if (selectedGroupId === -1) return ['ungrouped'];
    return [`group-${selectedGroupId}`];
  }, [selectedGroupId]);

  return (
    <div style={{ width: 260, minWidth: 260 }}>
      <div className="gaf-mb-sm">
        {creating ? (
          <div className="gaf-flex gaf-gap-xs">
            <Input
              size="small"
              placeholder="分组名称"
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              onPressEnter={handleCreate}
            />
            <Button size="small" onClick={handleCreate}>
              确定
            </Button>
            <Button
              size="small"
              onClick={() => {
                setCreating(false);
                setNewGroupName('');
              }}
            >
              取消
            </Button>
          </div>
        ) : (
          <Button type="dashed" size="small" block icon={<PlusOutlined />} onClick={() => setCreating(true)}>
            新建分组
          </Button>
        )}
      </div>

      <Tree
        treeData={treeData}
        titleRender={titleRender}
        selectedKeys={selectedKeys}
        onSelect={handleSelect as (keys: React.Key[], info: unknown) => void}
        blockNode
        defaultExpandAll
        style={{ background: 'transparent' }}
      />
    </div>
  );
}

export default DeviceGroupManager;
