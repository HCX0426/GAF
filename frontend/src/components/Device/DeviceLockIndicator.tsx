/**
 * device lock status group?
 * show device lock status, provides lock unlock / force unlock operation
 */
import { useState } from 'react';
import { Button, Tooltip, App, theme as antTheme } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { lockDevice, unlockDevice } from '@/api/devices';
import { useAuthStore } from '@/stores/useAuthStore';
import type { Device } from '@/types/models';
import { useTranslation } from '@/i18n';

/** DeviceLockIndicator component property?*/
interface DeviceLockIndicatorProps {
  device: Device;
  onLockChange?: () => void;
}

/**
 * device lock status indicator
 * based on lock status and current user role, show lock icon or lock/unlock/force-unlock action buttons
 */
export function DeviceLockIndicator({ device, onLockChange }: DeviceLockIndicatorProps) {
  const { message, modal } = App.useApp();
  const t = useTranslation();
  const { token } = antTheme.useToken();
  const user = useAuthStore((s) => s.user);
  const [loading, setLoading] = useState(false);

  const isLocked = !!device.locked_by_username;
  const isLockedByMe = isLocked && user != null && device.locked_by_username === user.username;
  const isAdmin = user?.role === 'admin';

  /** execute lock operation and notify parent component refresh */
  const handleLock = async () => {
    setLoading(true);
    try {
      await lockDevice(device.id);
      message.success(t('devices.device_locked'));
      onLockChange?.();
    } catch {
      message.error(t('devices.lock_device_failed'));
    } finally {
      setLoading(false);
    }
  };

  /** execute unlock operation and notify parent component refresh */
  const handleUnlock = async (force = false) => {
    setLoading(true);
    try {
      await unlockDevice(device.id, force);
      message.success(force ? t('devices.force_unlocked') : t('devices.device_unlocked'));
      onLockChange?.();
    } catch {
      message.error(force ? t('devices.force_unlock_failed') : t('devices.unlock_device_failed'));
    } finally {
      setLoading(false);
    }
  };

  /** execute force unlock after confirmation dialog */
  const handleForceUnlock = () => {
    modal.confirm({
      title: '强制解锁',
      content: `确定要强制解锁设备�?{device.name}」吗？该设备当前被�?{device.locked_by_username}」锁定。`,
      okText: '强制解锁',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => handleUnlock(true),
    });
  };

  if (!isLocked) {
    return (
      <Button loading={loading} onClick={handleLock}>
        锁定设备
      </Button>
    );
  }

  if (isLockedByMe) {
    return (
      <Button loading={loading} onClick={() => handleUnlock(false)}>
        解锁设备
      </Button>
    );
  }

  return (
    <Tooltip title={`已被 ${device.locked_by_username} 锁定${isAdmin ? '，可使用强制解锁' : ''}`}>
      <span className="gaf-gap-sm gaf-inline-flex" style={{ alignItems: 'center' }}>
        <LockOutlined className="gaf-text-md" style={{ color: token.colorWarning }} />
        {isAdmin && (
          <Button danger loading={loading} size="small" onClick={handleForceUnlock}>
            强制解锁
          </Button>
        )}
      </span>
    </Tooltip>
  );
}

export default DeviceLockIndicator;
