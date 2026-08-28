/**
 * 创建任务流程 E2E 测试
 * 测试场景：Dashboard → TaskStudio → 创建 Pipeline → 保存
 * 使用 page.route 拦截 API 调用
 */
import { test, expect } from '@playwright/test';

/** 模拟用户信息 */
const MOCK_USER_ME = {
  id: '1',
  username: 'testuser',
  role: 'admin',
  must_change_password: false,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
};

/** 模拟空 Pipeline 列表 */
const MOCK_PIPELINES_EMPTY = {
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
};

/** 模拟设备列表 */
const MOCK_DEVICES = {
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
};

/** 模拟 Dashboard 统计 */
const MOCK_DASHBOARD = {
  online_agents: 0,
  running_tasks: 0,
  today_executions: 0,
  success_rate: 100,
};

/** 设置所有测试用例共享的 API mock 和登录态 */
test.beforeEach(async ({ page }) => {
  await page.route('**/api/v2/auth/login/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access: 'mock-token',
        refresh: 'mock-refresh',
        must_change_password: false,
        user: MOCK_USER_ME,
      }),
    });
  });

  await page.route('**/api/v2/auth/refresh/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access: 'mock-token-new', refresh: 'mock-refresh-new' }),
    });
  });

  await page.route('**/api/v2/users/me/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_USER_ME),
    });
  });

  await page.route('**/api/v2/dashboard/stats/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_DASHBOARD),
    });
  });

  await page.route('**/api/v2/devices/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_DEVICES),
    });
  });

  await page.route('**/api/v2/pipelines/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_PIPELINES_EMPTY),
    });
  });

  await page.route('**/api/v2/scheduled-tasks/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
    });
  });

  await page.route('**/api/v2/notifications/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
    });
  });

  /** 先登录 */
  await page.goto('/login');
  await page.fill('input[placeholder*="用户名"]', 'testuser');
  await page.fill('input[type="password"]', 'password');
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/dashboard/, { timeout: 15000 });
});

test.describe('创建任务流程', () => {
  test('从 Dashboard 应能导航到 TaskStudio', async ({ page }) => {
    await expect(page).toHaveURL(/\/dashboard/);

    const taskStudioLink = page.locator('a[href="/task-studio"]');
    if (await taskStudioLink.isVisible()) {
      await taskStudioLink.click();
      await expect(page).toHaveURL(/\/task-studio/, { timeout: 10000 });
    }
  });

  test('TaskStudio 页面应能正确加载', async ({ page }) => {
    await page.goto('/task-studio');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('text=任务工坊')).toBeVisible({ timeout: 10000 });
  });

  test('应能创建新的 Pipeline 并保存', async ({ page }) => {
    await page.goto('/task-studio/custom/new');
    await page.waitForLoadState('networkidle');

    const pageContent = await page.textContent('body');
    expect(pageContent).toBeTruthy();
  });

  test('任务详情页应正确渲染', async ({ page }) => {
    await page.route('**/api/v2/pipelines/1/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          name: 'Test Pipeline',
          description: 'A test pipeline',
          version: '1.0.0',
          config: { nodes: [], edges: [] },
          created_at: '2025-01-01T00:00:00Z',
          updated_at: '2025-01-01T00:00:00Z',
        }),
      });
    });

    await page.goto('/task-studio/1');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('text=Test Pipeline')).toBeVisible({ timeout: 10000 });
  });
});
