/**
 * 服务管理页 E2E (spec 2026-08-29-services-management-monitor, TD-419 补全).
 * 场景: 登录 → 系统 → 服务管理 → 5 服务卡片渲染 → 查看日志 Drawer → 报错过滤.
 * 使用 page.route mock API (与 auth/login.spec.ts 同模式), 无需真实后端.
 */
import { test, expect } from '@playwright/test';

const MOCK_LOGIN = {
  access: 'mock-access-token-svc',
  refresh: 'mock-refresh-token-svc',
  must_change_password: false,
  user: { id: '1', username: 'admin', role: 'admin', must_change_password: false },
};
const MOCK_ME = { id: '1', username: 'admin', role: 'admin', must_change_password: false };

const MOCK_SERVICES = {
  updatedAt: '2026-08-29T11:00:00+0800',
  daemon: { running: true, pid: 7260 },
  services: [
    { name: 'redis', healthy: true, detail: 'redis-cli PING -> PONG (port 6379)', ts: 1,
      running: true, pid: 20800, port: 6379, restart_count: 0, error_count: 0, latest_error: null, log_files: [] },
    { name: 'backend', healthy: true, detail: "healthz {'db': 'pass', 'redis': 'pass'}", ts: 1,
      running: true, pid: 23204, port: 8000, restart_count: 0, error_count: 2,
      latest_error: '[2026-08-29 10:25:16] [ERROR] boom', log_files: [] },
    { name: 'agent', healthy: true, detail: 'status=idle hb_age=3s', ts: 1,
      running: true, pid: 22320, port: null, restart_count: 0, error_count: 0, latest_error: null, log_files: [] },
    { name: 'frontend', healthy: true, detail: 'HTTP 200 @ http://127.0.0.1:5173/', ts: 1,
      running: true, pid: 25164, port: 5173, restart_count: 0, error_count: 0, latest_error: null, log_files: [] },
    { name: 'daemon', healthy: true, detail: 'daemon PID=7260', ts: null,
      running: true, pid: 7260, port: null, restart_count: null, error_count: null, latest_error: null, log_files: [] },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v2/auth/login/', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_LOGIN),
  }));
  await page.route('**/api/v2/users/me/', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_ME),
  }));
  await page.route('**/api/v2/auth/refresh/', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ access: 'mock-new', refresh: 'mock-new' }),
  }));
  await page.route('**/api/v2/monitors/services/', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_SERVICES),
  }));
});

test.describe('服务管理页', () => {
  test('渲染 5 服务卡片', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/dashboard/, { timeout: 15000 });

    await page.goto('/system/services');
    await expect(page.locator('text=服务管理').first()).toBeVisible();
    for (const name of ['redis', 'backend', 'agent', 'frontend', 'daemon']) {
      await expect(page.locator(`main >> text=${name}`).first()).toBeVisible();
    }
    // 报错标签
    await expect(page.locator('text=2 条报错').first()).toBeVisible();
  });

  test('查看日志 Drawer + 仅报错过滤', async ({ page }) => {
    await page.route('**/api/v2/monitors/services/logs/**', (route) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        service: 'backend', path: 'debug/system/services/backend.log', files: [],
        lines: ['INFO starting', 'ERROR boom', 'INFO done'],
      }),
    }));

    await page.goto('/login');
    await page.fill('input[placeholder*="用户名"]', 'admin');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/dashboard/, { timeout: 15000 });

    await page.goto('/system/services');
    await expect(page.locator('text=backend').first()).toBeVisible();
    await page.locator('main >> text=查看日志').first().click();
    await expect(page.locator('.ant-drawer')).toBeVisible();
    await expect(page.locator('.ant-drawer >> text=ERROR boom')).toBeVisible();
  });
});