/**
 * 登录流程 E2E 测试
 * 测试场景：用户访问登录页 → 输入凭据 → 登录成功 → JWT 存储 → 跳转 Dashboard
 * 使用 page.route 拦截 API 调用，无需实际后端运行
 */
import { test, expect } from '@playwright/test';

/** 模拟登录 API 响应 */
const MOCK_LOGIN_RESPONSE = {
  access: 'mock-access-token-abc123',
  refresh: 'mock-refresh-token-xyz789',
  must_change_password: false,
  user: {
    id: '1',
    username: 'testuser',
    role: 'admin',
    must_change_password: false,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
};

/** 模拟用户信息 API 响应 */
const MOCK_USER_ME_RESPONSE = {
  id: '1',
  username: 'testuser',
  role: 'admin',
  must_change_password: false,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
};

/** 设置所有测试用例共享的 API mock */
test.beforeEach(async ({ page }) => {
  await page.route('**/api/v2/auth/login/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_LOGIN_RESPONSE),
    });
  });

  await page.route('**/api/v2/users/me/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_USER_ME_RESPONSE),
    });
  });

  await page.route('**/api/v2/auth/refresh/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access: 'mock-new-access-token',
        refresh: 'mock-new-refresh-token',
      }),
    });
  });
});

test.describe('登录流程', () => {
  test('用户应能正常登录并跳转到 Dashboard', async ({ page }) => {
    await page.goto('/login');

    await expect(page.locator('text=GAF')).toBeVisible();

    await page.fill('input[placeholder*="用户名"]', 'testuser');
    await page.fill('input[type="password"]', 'password123');

    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 });
  });

  test('登录成功后 JWT Token 应存储到 localStorage', async ({ page }) => {
    await page.goto('/login');

    await page.fill('input[placeholder*="用户名"]', 'testuser');
    await page.fill('input[type="password"]', 'password123');
    await page.click('button[type="submit"]');

    await page.waitForURL(/\/dashboard/, { timeout: 15000 });

    const refreshToken = await page.evaluate(() => localStorage.getItem('gaf_refresh_token'));
    expect(refreshToken).toBeTruthy();
  });

  test('登录成功后应显示侧边栏导航', async ({ page }) => {
    await page.goto('/login');

    await page.fill('input[placeholder*="用户名"]', 'testuser');
    await page.fill('input[type="password"]', 'password123');
    await page.click('button[type="submit"]');

    await page.waitForURL(/\/dashboard/, { timeout: 15000 });

    await expect(page.locator('aside')).toBeVisible();
  });

  test('未登录用户访问受保护页面应重定向到登录页', async ({ page }) => {
    await page.goto('/dashboard');

    await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
  });
});

test.describe('登录失败场景', () => {
  test('输入错误凭据应显示错误消息', async ({ page }) => {
    await page.route('**/api/v2/auth/login/', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '用户名或密码错误' }),
      });
    });

    await page.goto('/login');

    await page.fill('input[placeholder*="用户名"]', 'wronguser');
    await page.fill('input[type="password"]', 'wrongpass');
    await page.click('button[type="submit"]');

    await expect(page.locator('.ant-message-error')).toBeVisible({ timeout: 5000 });
  });
});
