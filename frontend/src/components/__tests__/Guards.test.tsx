/**
 * TD-336: Guard 组件测试 — RBAC 前端最后防线
 * 覆盖 AuthGuard / PermissionGuard / RoleGuard 三个组件
 * 测试 viewer / operator / admin 三种角色的允许/拒绝分支
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthGuard } from '@/components/Guards/AuthGuard';
import { PermissionGuard } from '@/components/Guards/PermissionGuard';
import { RoleGuard } from '@/components/Guards/RoleGuard';
import { useAuthStore } from '@/stores/useAuthStore';

/** 测试用户工厂 */
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

/** 重置 auth store 状态 */
beforeEach(() => {
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    isRefreshing: false,
    accessToken: null,
  });
});

// =============================================
// AuthGuard
// =============================================
describe('AuthGuard', () => {
  it('已认证时应渲染子组件', async () => {
    useAuthStore.setState({ isAuthenticated: true, isRefreshing: false });
    const { getByText } = render(
      <MemoryRouter>
        <AuthGuard>
          <div>受保护内容</div>
        </AuthGuard>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(getByText('受保护内容')).toBeDefined();
    });
  });

  it('未认证时应重定向到 /login', async () => {
    useAuthStore.setState({ isAuthenticated: false, isRefreshing: false });
    const { queryByText } = render(
      <MemoryRouter>
        <AuthGuard>
          <div>受保护内容</div>
        </AuthGuard>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(queryByText('受保护内容')).toBeNull();
    });
  });

  it('正在刷新 token 时应显示加载状态', () => {
    useAuthStore.setState({ isAuthenticated: false, isRefreshing: true });
    const { queryByText } = render(
      <MemoryRouter>
        <AuthGuard>
          <div>受保护内容</div>
        </AuthGuard>
      </MemoryRouter>,
    );
    // 正在刷新时不应渲染子组件
    expect(queryByText('受保护内容')).toBeNull();
  });
});

// =============================================
// PermissionGuard
// =============================================
describe('PermissionGuard', () => {
  it('admin 角色应拥有所有权限，渲染子组件', () => {
    useAuthStore.setState({ user: makeUser('admin') as never });
    const { getByText } = render(
      <PermissionGuard permission="device.control">
        <div>admin 内容</div>
      </PermissionGuard>,
    );
    expect(getByText('admin 内容')).toBeDefined();
  });

  it('operator 角色拥有 device.control 权限，应渲染子组件', () => {
    useAuthStore.setState({ user: makeUser('operator') as never });
    const { getByText } = render(
      <PermissionGuard permission="device.control">
        <div>operator 内容</div>
      </PermissionGuard>,
    );
    expect(getByText('operator 内容')).toBeDefined();
  });

  it('viewer 角色无 device.control 权限，应渲染 fallback (默认 null)', () => {
    useAuthStore.setState({ user: makeUser('viewer') as never });
    const { queryByText } = render(
      <PermissionGuard permission="device.control">
        <div>viewer 不应看到</div>
      </PermissionGuard>,
    );
    expect(queryByText('viewer 不应看到')).toBeNull();
  });

  it('viewer 角色有 device.view 权限，应渲染子组件', () => {
    useAuthStore.setState({ user: makeUser('viewer') as never });
    const { getByText } = render(
      <PermissionGuard permission="device.view">
        <div>viewer 只读内容</div>
      </PermissionGuard>,
    );
    expect(getByText('viewer 只读内容')).toBeDefined();
  });

  it('权限不足时应渲染自定义 fallback', () => {
    useAuthStore.setState({ user: makeUser('viewer') as never });
    const { getByText } = render(
      <PermissionGuard permission="task.execute" fallback={<div>无权限提示</div>}>
        <div>不应渲染</div>
      </PermissionGuard>,
    );
    expect(getByText('无权限提示')).toBeDefined();
  });
});

// =============================================
// RoleGuard
// =============================================
describe('RoleGuard', () => {
  it('admin 角色在允许列表中，应渲染子组件', () => {
    useAuthStore.setState({ user: makeUser('admin') as never });
    const { getByText } = render(
      <RoleGuard allowedRoles={['admin']}>
        <div>admin 专属页面</div>
      </RoleGuard>,
    );
    expect(getByText('admin 专属页面')).toBeDefined();
  });

  it('operator 角色在允许列表中，应渲染子组件', () => {
    useAuthStore.setState({ user: makeUser('operator') as never });
    const { getByText } = render(
      <RoleGuard allowedRoles={['admin', 'operator']}>
        <div>管理页面</div>
      </RoleGuard>,
    );
    expect(getByText('管理页面')).toBeDefined();
  });

  it('viewer 角色不在允许列表中，应显示 403', () => {
    useAuthStore.setState({ user: makeUser('viewer') as never });
    const { queryByText, getByText } = render(
      <RoleGuard allowedRoles={['admin', 'operator']}>
        <div>不应渲染</div>
      </RoleGuard>,
    );
    expect(queryByText('不应渲染')).toBeNull();
    expect(getByText('403')).toBeDefined();
  });

  it('用户为 null 时应显示 403', () => {
    useAuthStore.setState({ user: null });
    const { queryByText, getByText } = render(
      <RoleGuard allowedRoles={['admin']}>
        <div>不应渲染</div>
      </RoleGuard>,
    );
    expect(queryByText('不应渲染')).toBeNull();
    expect(getByText('403')).toBeDefined();
  });

  it('角色不在允许列表中时应显示自定义消息', () => {
    useAuthStore.setState({ user: makeUser('viewer') as never });
    const { getByText } = render(
      <RoleGuard allowedRoles={['admin']} fallbackMessage="需要管理员权限">
        <div>不应渲染</div>
      </RoleGuard>,
    );
    expect(getByText('需要管理员权限')).toBeDefined();
  });
});
