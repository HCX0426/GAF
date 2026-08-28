/**
 * fine-grained permission guard component
 * check user is no has has specified operation permission, no permission when hide child component or show prompt
 */
import { type ReactNode } from 'react';
import { usePermission } from '@/hooks/usePermission';

/** PermissionGuard component props */
interface PermissionGuardProps {
  children: ReactNode;
  permission: string;
  fallback?: ReactNode;
}

/**
 * fine-grained permission guard
 * used for control button, menu etc. UI element visibility
 */
export function PermissionGuard({ children, permission, fallback = null }: PermissionGuardProps) {
  const { hasPermission } = usePermission();

  if (!hasPermission(permission)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}

export default PermissionGuard;
