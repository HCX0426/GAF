/**
 * TD-336 #2: Login 页面 smoke 测试
 * 覆盖: 渲染不崩溃 / 登录表单可见 / 已认证时重定向
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { App } from 'antd';
import { LoginPage } from '@/pages/Login/index';
import { useAuthStore } from '@/stores/useAuthStore';

// Mock auth API
vi.mock('@/api/auth', () => ({
  register: vi.fn(),
  getOAuthUrl: vi.fn(),
  requestPasswordReset: vi.fn(),
  confirmPasswordReset: vi.fn(),
  getInitStatus: vi.fn().mockResolvedValue({ register_enabled: true }),
}));

// Mock password strength (zxcvbn is heavy)
vi.mock('@/utils/passwordStrength', () => ({
  evaluatePasswordStrength: () => ({
    percent: 0,
    label: '弱',
    colorToken: 'colorError',
    crackTime: 'instant',
    suggestions: [],
  }),
}));

beforeEach(() => {
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    isRefreshing: false,
    requires2FA: false,
    mustChangePassword: false,
    loading: false,
  });
});

describe('LoginPage', () => {
  it('应渲染登录表单 (Tab + 用户名/密码输入框)', () => {
    render(
      <App>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </App>,
    );
    // Tab 标签 "登录" (zh-CN 默认)
    expect(screen.getByText('登录')).toBeDefined();
    // 用户名输入框 (placeholder)
    expect(screen.getByPlaceholderText('用户名')).toBeDefined();
    // 密码输入框 (placeholder)
    expect(screen.getByPlaceholderText('密码')).toBeDefined();
  });

  it('未认证时不应重定向到 /dashboard', () => {
    const { container } = render(
      <App>
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/dashboard" element={<div>Dashboard 页面</div>} />
          </Routes>
        </MemoryRouter>
      </App>,
    );
    // 未认证时应停留在 login 页面
    expect(container.querySelector('input[placeholder="用户名"]')).not.toBeNull();
  });

  it('已认证时应重定向到 /dashboard', async () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: { id: 1, username: 'testuser', role: 'admin' } as never,
    });

    render(
      <App>
        <MemoryRouter initialEntries={['/login']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/dashboard" element={<div>Dashboard 页面</div>} />
          </Routes>
        </MemoryRouter>
      </App>,
    );

    await waitFor(() => {
      expect(screen.getByText('Dashboard 页面')).toBeDefined();
    });
  });

  it('输入用户名和密码后提交应调用 store.login', async () => {
    const loginSpy = vi.fn().mockResolvedValue(undefined);
    useAuthStore.setState({ login: loginSpy } as never);

    const { container } = render(
      <App>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </App>,
    );

    const usernameInput = screen.getByPlaceholderText('用户名');
    const passwordInput = screen.getByPlaceholderText('密码');

    fireEvent.change(usernameInput, { target: { value: 'testuser' } });
    fireEvent.change(passwordInput, { target: { value: 'testpass123' } });

    // 找到登录表单的提交按钮 (htmlType="submit")
    // 直接通过 DOM 查询避免匹配到 OAuth 按钮 (使用 GitHub/Google 登录)
    const submitBtn = container.querySelector('button[type="submit"]') as HTMLButtonElement;
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(loginSpy).toHaveBeenCalledWith('testuser', 'testpass123', false);
    });
  });
});
