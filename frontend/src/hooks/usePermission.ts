/**
 * permission check Hook
 * based on user role provides operation permission judge capability
 */
import { useCallback } from 'react';
import { useAuthStore } from '@/stores/useAuthStore';

/**
 * role to permission mapping table
 * admin has has has permission,operator has has operation types permission, viewer can only view
 */
const ROLE_PERMISSIONS: Record<string, string[]> = {
  admin: ['*'],
  operator: [
    'device.view',
    'device.control',
    'task.view',
    'task.create',
    'task.execute',
    'execution.view',
    'execution.cancel',
    'monitor.view',
    'monitor.manage',
    'resource.view',
    'resource.upload',
    'debug.view',
    'debug.upload',
    'qa.view',
    'qa.ask',
    'schedule.view',
    'schedule.create',
    'settings.view',
  ],
  viewer: [
    'device.view',
    'task.view',
    'execution.view',
    'monitor.view',
    'resource.view',
    'debug.view',
    'qa.view',
    'schedule.view',
    'settings.view',
  ],
};

/** usePermission Hook return value type */
interface UsePermissionResult {
  hasPermission: (permission: string) => boolean;
  userRole: string;
  permissions: string[];
}

/**
 * get current user permission judge capability
 */
export function usePermission(): UsePermissionResult {
  const user = useAuthStore((s) => s.user);
  /** development environment or no role when default admin, ensure has menu can visible; production environment corresponding via login API get true real role */
  const userRole = user?.role ?? (import.meta.env.DEV ? 'admin' : 'viewer');
  const permissions = ROLE_PERMISSIONS[userRole] ?? ROLE_PERMISSIONS.viewer;

  /** check is no has has specified permission */
  const hasPermission = useCallback(
    (permission: string): boolean => {
      if (permissions.includes('*')) return true;
      return permissions.includes(permission);
    },
    [permissions],
  );

  return { hasPermission, userRole, permissions };
}
