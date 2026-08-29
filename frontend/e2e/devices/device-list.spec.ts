/**
 * Device list E2E tests
 * Scenarios: device grid loads, detail panel opens on card click,
 *            emulator scan discovers LDPlayer, screenshot test on online device
 * Uses page.route to mock API calls — no backend required
 */
import { test, expect } from '@playwright/test';

/** Mocked user info (admin role so all routes are accessible) */
const MOCK_USER_ME = {
  id: '1',
  username: 'testuser',
  role: 'admin',
  must_change_password: false,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
};

/** Mocked device list — one online emulator + one offline emulator */
const MOCK_DEVICES = {
  items: [
    {
      id: 1,
      name: 'LDPlayer-01',
      device_type: 'emulator',
      status: 'online',
      agent: 1,
      agent_info: {
        id: 1,
        agent_id: 'agent-1',
        hostname: 'test-host',
        ip_address: '127.0.0.1',
        status: 'online',
        last_heartbeat: '2025-01-01T00:00:00Z',
      },
      resolution_width: 1080,
      resolution_height: 1920,
      resolution: { width: 1080, height: 1920 },
      screenshot_fps: 10,
      extra_info: {},
      locked_by: null,
      locked_by_username: null,
      locked_at: null,
      control_mode: 'foreground',
      screenshot_method: 'auto',
      input_method: 'SendInput',
      device_stats: {},
      adb_serial: '127.0.0.1:5555',
      window_handle: '',
      emulator_brand: 'ldplayer',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
    },
    {
      id: 2,
      name: 'BlueStacks-02',
      device_type: 'emulator',
      status: 'offline',
      agent: null,
      agent_info: null,
      resolution_width: 1280,
      resolution_height: 720,
      resolution: { width: 1280, height: 720 },
      screenshot_fps: 0,
      extra_info: {},
      locked_by: null,
      locked_by_username: null,
      locked_at: null,
      control_mode: 'foreground',
      screenshot_method: 'auto',
      input_method: 'SendInput',
      device_stats: {},
      adb_serial: '127.0.0.1:5557',
      window_handle: '',
      emulator_brand: 'bluestacks',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
};

/** Mocked scan response — discovers one LDPlayer instance */
const MOCK_SCAN_RESPONSE = {
  android: [
    {
      name: 'LDPlayer-0',
      emulator: 'ldplayer',
      adb_port: 5555,
      adb_serial: '127.0.0.1:5555',
      status: 'discovered',
      android_version: 'Android 9',
      resolution: { width: 1080, height: 1920 },
    },
  ],
  windows: [],
};

/** Mocked screenshot test result — 1x1 PNG, success */
const MOCK_SCREENSHOT_RESULT = {
  screenshot_base64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  latency_ms: 45,
  fps: 22,
  resolution: { width: 1080, height: 1920 },
  screenshot_method: 'minicap',
  available_methods: ['auto', 'minicap', 'adb'],
  success: true,
  error: null,
};

/** Empty pagination payload used for unrelated list endpoints */
const EMPTY_PAGINATED = { items: [], total: 0, page: 1, page_size: 20 };

/** Shared API mocks + login flow */
test.beforeEach(async ({ page }) => {
  // Auth mocks
  await page.route('**/api/v2/auth/login/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access: 'mock-access-token',
        refresh: 'mock-refresh-token',
        must_change_password: false,
        user: MOCK_USER_ME,
      }),
    });
  });

  await page.route('**/api/v2/auth/refresh/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access: 'mock-access-token-new',
        refresh: 'mock-refresh-token-new',
      }),
    });
  });

  await page.route('**/api/v2/users/me/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_USER_ME),
    });
  });

  // Device API — single catch-all with URL-based branching for scan / test-screenshot / list
  await page.route('**/api/v2/devices/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/scan/')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SCAN_RESPONSE),
      });
    } else if (url.match(/\/devices\/\d+\/test-screenshot\//)) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SCREENSHOT_RESULT),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DEVICES),
      });
    }
  });

  // Other list endpoints called on mount / by layout — return empty to keep DOM clean
  await page.route('**/api/v2/device-groups/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY_PAGINATED),
    });
  });

  await page.route('**/api/v2/agents/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY_PAGINATED),
    });
  });

  await page.route('**/api/v2/dashboard/stats/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        online_agents: 0,
        running_tasks: 0,
        today_executions: 0,
        success_rate: 100,
      }),
    });
  });

  await page.route('**/api/v2/notifications/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY_PAGINATED),
    });
  });

  await page.route('**/api/v2/scheduled-tasks/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EMPTY_PAGINATED),
    });
  });

  // Login before each test so /devices is reachable
  await page.goto('/login');
  await page.fill('input[placeholder*="用户名"]', 'testuser');
  await page.fill('input[type="password"]', 'password');
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/dashboard/, { timeout: 15000 });
});

test.describe('设备列表', () => {
  test('设备网格应加载并展示已注册设备', async ({ page }) => {
    await page.goto('/devices');
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('LDPlayer-01')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('BlueStacks-02')).toBeVisible({ timeout: 10000 });
  });

  test('点击设备卡片应打开详情面板', async ({ page }) => {
    await page.goto('/devices');
    await page.waitForLoadState('networkidle');

    await page.getByText('LDPlayer-01').first().click();

    // DeviceDetailPanel renders an Antd Drawer
    await expect(page.locator('.ant-drawer')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.ant-drawer').getByText('LDPlayer-01')).toBeVisible({ timeout: 5000 });
  });

  test('扫描模拟器应发现本地 LDPlayer 实例', async ({ page }) => {
    await page.goto('/devices');
    await page.waitForLoadState('networkidle');

    await page.getByRole('button', { name: '扫描模拟器' }).click();

    // ScanModal title is hard-coded English
    await expect(page.getByText('Scan Emulators')).toBeVisible({ timeout: 10000 });
    // Scan runs through 7 simulated stages (~2.5s) before the API call resolves
    await expect(page.getByText('LDPlayer-0')).toBeVisible({ timeout: 15000 });
  });

  test('在线设备应能执行截图测试', async ({ page }) => {
    await page.goto('/devices');
    await page.waitForLoadState('networkidle');

    // Switch to table view (Segmented with UnorderedListOutlined icon)
    await page.locator('.ant-segmented-item:has(.anticon-unordered-list)').click();

    // Click the first "测试截图" button in the table action column
    await page.getByRole('button', { name: '测试截图' }).first().click();

    // ScreenshotTester modal title is "测试截图 - {deviceName}"
    await expect(page.getByText('测试截图 - LDPlayer-01')).toBeVisible({ timeout: 5000 });
  });
});
