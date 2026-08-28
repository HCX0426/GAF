/**
 * TD-336: usePermission hook 测试 — RBAC 权限判断逻辑
 * 覆盖 admin/operator/viewer 三种角色的权限映射和 hasPermission 判断
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePermission } from '@/hooks/usePermission';
import { useAuthStore } from '@/stores/useAuthStore';

const makeUser = (role: 'admin' | 'operator' | 'viewer') => ({
  id: 1,
  username: 'testuser',
  role,
  must_change_password: false,
  is_active: true,
  is_first_login: false,
  totp_enabled: false,
  last_login: null,
  created_at: '2026-01-01T00:00:00Z',
});

beforeEach(() => {
  useAuthStore.setState({ user: null });
});

describe('usePermission', () => {
  describe('admin 角色', () => {
    beforeEach(() => {
      useAuthStore.setState({ user: makeUser('admin') as never });
    });

    it('userRole 应为 admin', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.userRole).toBe('admin');
    });

    it('hasPermission 对任意权限应返回 true (通配符 *)', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.hasPermission('device.control')).toBe(true);
      expect(result.current.hasPermission('any.unknown.permission')).toBe(true);
      expect(result.current.hasPermission('system.admin.delete')).toBe(true);
    });

    it('permissions 应为 ["*"]', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.permissions).toEqual(['*']);
    });
  });

  describe('operator 角色', () => {
    beforeEach(() => {
      useAuthStore.setState({ user: makeUser('operator') as never });
    });

    it('userRole 应为 operator', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.userRole).toBe('operator');
    });

    it('hasPermission 对 device.control 应返回 true', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.hasPermission('device.control')).toBe(true);
    });

    it('hasPermission 对 device.view 应返回 true', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.hasPermission('device.view')).toBe(true);
    });

    it('hasPermission 对 task.execute 应返回 true', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.hasPermission('task.execute')).toBe(true);
    });

    it('hasPermission 对未授权权限应返回 false', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.hasPermission('user.delete')).toBe(false);
      expect(result.current.hasPermission('system.config')).toBe(false);
    });

    it('permissions 应包含操作类权限', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.permissions).toContain('device.control');
      expect(result.current.permissions).toContain('task.execute');
      expect(result.current.permissions).toContain('monitor.manage');
      expect(result.current.permissions).not.toContain('*');
    });
  });

  describe('viewer 角色', () => {
    beforeEach(() => {
      useAuthStore.setState({ user: makeUser('viewer') as never });
    });

    it('userRole 应为 viewer', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.userRole).toBe('viewer');
    });

    it('hasPermission 对只读权限应返回 true', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.hasPermission('device.view')).toBe(true);
      expect(result.current.hasPermission('task.view')).toBe(true);
      expect(result.current.hasPermission('execution.view')).toBe(true);
    });

    it('hasPermission 对写操作权限应返回 false', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.hasPermission('device.control')).toBe(false);
      expect(result.current.hasPermission('task.execute')).toBe(false);
      expect(result.current.hasPermission('monitor.manage')).toBe(false);
    });

    it('permissions 应仅包含 .view 类权限', () => {
      const { result } = renderHook(() => usePermission());
      expect(result.current.permissions).toContain('device.view');
      expect(result.current.permissions).toContain('task.view');
      expect(result.current.permissions).not.toContain('device.control');
      expect(result.current.permissions).not.toContain('*');
    });
  });

  describe('用户为 null', () => {
    beforeEach(() => {
      useAuthStore.setState({ user: null });
    });

    it('vitest (DEV) 环境应回退为 admin (开发默认)', () => {
      // usePermission.ts L31: user?.role ?? (import.meta.env.DEV ? 'admin' : 'viewer')
      // vitest 运行在 DEV 模式, 所以回退为 admin
      const { result } = renderHook(() => usePermission());
      expect(result.current.userRole).toBe('admin');
    });
  });
});
