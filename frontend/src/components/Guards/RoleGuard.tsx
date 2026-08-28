/**
 * role route guard component
 * check user role is no in allow list in, mismatch when show no permission page
 */
import { type ReactNode } from 'react';
import { Result } from 'antd';
import { useAuthStore } from '@/stores/useAuthStore';

/** RoleGuard component props */
interface RoleGuardProps {
  children: ReactNode;
  allowedRoles: string[];
  fallbackMessage?: string;
}

/** role route guard */
export function RoleGuard({ children, allowedRoles, fallbackMessage = '您没有访问此页面的权限' }: RoleGuardProps) {
  const user = useAuthStore((s) => s.user);

  if (!user || !user.role || !allowedRoles.includes(user.role)) {
    return <Result status="403" title="403" subTitle={fallbackMessage} />;
  }

  return <>{children}</>;
}

export default RoleGuard;
