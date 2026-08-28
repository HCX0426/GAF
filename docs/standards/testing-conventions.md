---
summary: 测试规范 — 四层测试（后端 pytest/Django TestCase + 前端 Vitest + E2E Playwright + agent 节点 pytest/MagicMock），约束 AI 写出格式一致的测试代码；验证优先级浏览器优先（用户指令 2026-08-27）
applies_to: [backend, frontend, testing, pytest, vitest, playwright]
last_updated: 2026-08-27
key_decisions:
  - 后端用 Django TestCase（DB 测试）/ SimpleTestCase（非 DB），pytest-django 兼容
  - 测试文件位置：<app>/tests/test_<module>.py；集成测试包 __init__.py 必含 TD-068 throttle 补丁
  - 前端用 Vitest + jsdom + @testing-library/react，测试文件同级 __tests__/
  - E2E 分两层：Python Playwright（scripts/e2e/scenarios/）+ TypeScript Playwright（frontend/e2e/）
  - 后端覆盖率 fail_under=30（pyproject.toml），前端 vitest 阈值 lines=40
  - 提交前跑覆盖率（project_rules §3.4 大阶段提交流程）
---

# GAF Testing Conventions

> **强制**：AI 写测试代码前必读。所有后端/前端/E2E 测试必须遵循本文规范。
> 配套：`docs/standards/backend-conventions.md` §9 + `docs/standards/frontend-conventions.md` §测试

## 1. 四层测试概览

| 层 | 框架 | 位置 | 运行命令 |
|----|------|------|---------|
| 后端单测 | Django TestCase / pytest-django | `backend/<app>/tests/test_<module>.py` | `conda run -n gaf python manage.py test` |
| 前端单测 | Vitest + jsdom + @testing-library/react | `frontend/src/<dir>/__tests__/<Component>.test.tsx` | `npm run test` / `npm run test:coverage` |
| E2E (Python) | Playwright (sync_playwright) | `scripts/e2e/scenarios/` | `python scripts/e2e/run_all.py <scenario>` |
| E2E (TypeScript) | @playwright/test (async) | `frontend/e2e/` | `npx playwright test` / `npm run e2e` |
| agent 节点测试 | pytest + MagicMock | `agent/tests/`（参考 `test_ocr.py`） | `D:\code\environment\conda\envs\gaf\python.exe -m pytest agent/tests/ -q` |

> **agent 节点测试层**：测试范围覆盖 agent 引擎节点（`template_match` / `OCR` / `click` / `wait` 等）。覆盖要求：节点关键方法（非 happy path）必须有单测（如 `_get_image` fallback / `execute` fail_result），详见 §7。

## 1.1 测试优先级：浏览器优先（用户指令 2026-08-27）

> **用户指令**: "以后测试优先使用浏览器进行测试"（2026-08-27，E2E 补救方案 A 时提出）

- **验证优先级**：浏览器真实交互（Playwright）> API 冒烟 > 单元测试
- 凡涉及 UI / WS / Agent 交互的执行路径改动（调度、派发、状态流转、前端交互），
  完成任务后**先评估并优先**跑浏览器 E2E 冒烟（登录 → 触发 → 观察 → 断言 + 0 console error），
  再补 API / 单元测试；环境缺窗口/设备时，浏览器覆盖"前端交互 + WS 通道 + 状态展示"层，
  执行节点失败属环境限制需如实标注，不冒充通过
- 与 `project_rules §3.7` L3 循环（涉及 UI/WS/Agent 修改启动浏览器实测）一致，此处扩为**默认优先**
- 冒烟脚本落 `.trash/`（gitignore）不污染仓库；可复用的永久脚本落 `scripts/e2e/scenarios/`

### 1.1.1 测试浏览器策略：无头/IDE 内置（用户指令 2026-08-28）

> **用户指令**: "以后测试都走无头浏览器，或者 ide 的内置浏览器，不要影响我正常使用浏览器"
> 背景：AI 曾用 `Start-Process chrome` 打开宿主 Chrome 展示界面，打扰了用户正常浏览。

- **测试驱动浏览器一律 headless**（Playwright `headless=True`）或 TRAE **IDE 内置浏览器**（browser 工具），
  **禁止** `Start-Process` / 枚举宿主浏览器做"展示/看界面"用途
- 需要"看界面"时：产出截图（`.trash/evidence/`）或引导用户用 IDE 内置浏览器打开，**不碰宿主 Chrome**
- 例外：**被测窗口设备**（agent 需控制来执行任务的窗口，如 GAF 任务的 Chrome/游戏窗口）属测试环境对象，
  由 GAF 自身控制；若与用户浏览器冲突，优先选用隔离实例/显式提示
- 证据交付：截图 + 断言文本即可，不必弹真实窗口

## 2. 后端测试规范

### 2.1 TestCase 选择

- 用 `django.test.TestCase` 触及数据库的测试（每个测试包在事务中回滚）
- 用 `SimpleTestCase` 不触及数据库的纯逻辑测试
- pytest-django 已配置（`pyproject.toml [tool.pytest.ini_options]`），`DJANGO_SETTINGS_MODULE = "config.settings.test"`

### 2.2 文件位置与命名

```
backend/<app>/tests/
├── __init__.py          # 必含 TD-068 throttle 补丁（见 §5.1）
├── test_<module>.py     # 按被测模块拆分
└── factories.py         # factory_boy 工厂（可选，见 backend-conventions §9）
```

### 2.3 API 测试

- 用 `rest_framework.test.APIClient`，不用 Django `Client`
- 登录走 `/api/v2/accounts/auth/login/`（JWT），不用 `force_login` 跑真实认证链路
- 用户创建：优先用 factory_boy factory（见 `backend-conventions.md` §10），不用 `User.objects.create_user` 手写样板

```python
from rest_framework.test import APIClient
from accounts.factories import AdminUserFactory

class MyAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = AdminUserFactory()
        self.client.login(username=self.user.username, password="testpass123")

    def test_list_returns_200(self):
        resp = self.client.get("/api/v2/tasks/")
        self.assertEqual(resp.status_code, 200)
```

### 2.4 角色权限矩阵

测试三种角色的 CRUD 权限（见 api-contract.md §鉴权）：

| 角色 | 权限 |
|------|------|
| admin | 全部（CRUD + 执行） |
| operator | 执行 + 读，不可管理配置 |
| viewer | 只读 |

每个受保护端点至少测一次 "权限拒绝"（viewer 写 → 403）。

### 2.5 URL 存在性测试

枚举 `config.urls.urlpatterns`，断言每个路由返回预期状态码（200/401/405），防止路由误删：

```python
from django.urls import get_resolver

class URLRoutingTest(TestCase):
    def test_all_routes_resolve(self):
        for pattern in get_resolver().url_patterns:
            # assert pattern.name or callback exists
            ...
```

### 2.6 Mock Celery 任务

用 `unittest.mock.patch` 替换 `.delay`，断言被调用且不真正入队：

```python
from unittest.mock import patch

class TaskDispatchTest(TestCase):
    @patch("tasks.tasks.run_task.delay")
    def test_dispatch_enqueues(self, mock_delay):
        ...
        mock_delay.assert_called_once_with(task_id)
```

### 2.7 覆盖率

```powershell
conda run -n gaf coverage run manage.py test
conda run -n gaf coverage report
```

- 配置在 `pyproject.toml [tool.coverage.run]` / `[tool.coverage.report]`
- `fail_under = 30`（起步基线，逐步提高）
- `source = ["backend"]`，排除 migrations/tests/settings/admin/apps

## 3. 前端测试规范

### 3.1 框架与配置

- Vitest + jsdom + @testing-library/react（`frontend/vitest.config.ts`）
- `environment: "jsdom"`，`globals: true`，setupFiles: `src/test/setup.ts`
- include: `src/**/*.{test,spec}.{ts,tsx}`

### 3.2 文件位置

```
frontend/src/<dir>/
├── Component.tsx
└── __tests__/
    └── Component.test.tsx
```

### 3.3 全局 Mock（src/test/setup.ts）

已内置，勿重复定义：
- `ResizeObserver`（Antd/图表依赖）
- `window.matchMedia`（响应式断点）
- `window.getComputedStyle`（jsdom 不完整实现）

### 3.4 组件测试

用 `render` + `screen` queries（getByRole 优先，getByText 次之）：

```tsx
import { render, screen } from "@testing-library/react";
import DeviceCard from "../DeviceCard";

test("shows device name", () => {
  render(<DeviceCard name="PC-01" status="online" />);
  expect(screen.getByRole("heading", { name: "PC-01" })).toBeInTheDocument();
});
```

### 3.5 Hook 测试

用 `@testing-library/react` 的 `renderHook`：

```tsx
import { renderHook } from "@testing-library/react";
import { useDeviceStore } from "@/store/deviceStore";

test("initial state", () => {
  const { result } = renderHook(() => useDeviceStore());
  expect(result.current.devices).toEqual([]);
});
```

### 3.6 WebSocket Mock（两种模式）

- **Pattern A — wsClient 单例**：`vi.mock("@/websocket/client")` mock 整个 wsClient 模块，适用于通过封装层访问 WS 的组件
- **Pattern B — 直接 new WebSocket()**：`vi.stubGlobal("WebSocket", MockServer)` 用 mock-socket 造一个 MockServer 实例 stub 到全局，适用于直接调用原生 WebSocket 的代码

### 3.7 覆盖率

```powershell
npm run test:coverage
```

- 阈值起步：lines=40, branches=30, functions=35, statements=40（逐步提高）
- 提交前必跑（project_rules §3.4）

## 4. E2E 测试规范

### 4.1 框架与运行

- Playwright `sync_playwright`（非 async），headless 默认开
- 场景文件在 `scripts/e2e/scenarios/`（6 个 .py 场景文件），通过 `scripts/e2e/run_all.py <name>` 调用
- `run_all.py` 通过 `@register` 装饰器注册共 10 个场景：7 个内联定义在 `run_all.py`（cold_start / new_feature / bug_fix / documentation / refactor / cross_repo / collaboration）+ 3 个从 `scenarios/` 导入（browser_login / devices_control_mode / ai_qa_chat）

```powershell
# 单场景
conda run -n gaf python scripts/e2e/run_all.py browser_login

# 全部 10 场景
conda run -n gaf python scripts/e2e/run_all.py

# 非零退出码（CI 用）
conda run -n gaf python scripts/e2e/run_all.py --strict
```

### 4.2 编写规范

- headless 模式用于 CI，headed（`headless=False`）用于本地调试
- 通过 `page.on("console", ...)` 捕获 JS 错误，断言 `console_errors` 为空
- 登录用真实 API（`/api/v2/accounts/auth/login/`），不 mock 认证

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.goto("http://localhost:5173/login", wait_until="networkidle")
    # ... fill form, assert URL ...
    assert console_errors == []
    browser.close()
```

### 4.3 Chromium 安装

```powershell
conda run -n gaf python -m playwright install chromium
```

### 4.4 浏览器交互测试 (Playwright / browser-use)

浏览器自动化分两层：
- **Playwright（主推）**：规范 E2E、CI、跨平台、捕获 console 错误。GAF 已注册 `scripts/e2e/scenarios/browser_login.py` 场景。
- **browser-use（临时快速验证）**：CLI 式快速点击、截图。Windows 无 `bash` 时不可用，优先回退到 Playwright。

#### Playwright 快速验证

```powershell
# Ensure Chromium binary is installed
conda run -n gaf python -m playwright install chromium

# Run the bundled login smoke test
conda run -n gaf python scripts/e2e/run_all.py browser_login
```

Python snippet for ad-hoc checks:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.goto("http://localhost:5173/login", wait_until="networkidle")
    # Fill form, click, assert URL, then inspect console_errors
    browser.close()
```

#### browser-use 临时 CLI（可选）

PowerShell 中使用 browser-use 时需设置 `$env:PYTHONIOENCODING='utf-8'`:

```powershell
$env:PYTHONIOENCODING='utf-8'

# Check availability; on Windows without bash fall back to Playwright
browser-use doctor

# Open target page (ensure already logged in)
browser-use open http://localhost:5173/tasks

# Inspect clickable element indices
browser-use state

# Simulate interactions
browser-use click <index>
browser-use input <index> <text>

# Screenshot and console JS errors
browser-use screenshot
browser-use eval "JSON.stringify({jsErrors: window.__browserErrors?.length || 0})"
```

**交互元素覆盖要求**:
- 对每类元素 (button/tab/input/select/switch/modal/checkbox/radio 等) 至少执行一次操作
- Switch 做开/关双向测试; Select 做选项选择和清除测试
- Modal 做打开和关闭测试; 表格做展开行、分页、排序等测试
- 记录每个交互操作的执行结果 ✅/❌, 最后检查 JS 错误数

### 4.5 前端 E2E 测试（TypeScript Playwright）

> **与 §4.1 Python E2E 的分工**：GAF 有两套 Playwright E2E 测试，定位不同：
>
> | 维度 | `scripts/e2e/` (Python) | `frontend/e2e/` (TypeScript) |
> |------|------------------------|------------------------------|
> | 语言 | Python `sync_playwright` | TypeScript `@playwright/test` (async) |
> | 后端依赖 | **需要真实后端** + 真实认证（`/api/v2/accounts/auth/login/`） | **无需后端**，通过 `page.route` 拦截 mock API |
> | 测试焦点 | 全栈集成（前端 → 后端 → Agent → DB） | 前端 UI 流程（路由跳转 / 组件交互 / 状态管理） |
> | 运行环境 | 需启动 Django + Vite + Agent | 仅需 Vite dev server（`webServer` 自动启动） |
> | 适用场景 | 回归测试 / CI 全链路验证 | 前端独立开发 / 快速反馈 / 无后端环境验证 |

**目录结构**：

```
frontend/e2e/
├── playwright.config.ts       # 配置：Chromium headless + baseURL localhost:5173 + webServer 自动启动 Vite
├── auth/
│   └── login.spec.ts          # 登录流程：输入凭据 → JWT 存储 → 跳转 Dashboard
├── devices/
│   └── device-list.spec.ts    # 设备列表页交互
└── tasks/
    └── create.spec.ts         # 创建任务流程：Dashboard → TaskStudio → 创建 Pipeline → 保存
```

**配置要点**（`playwright.config.ts`）：

- `testDir: '.'` — 测试文件在 `frontend/e2e/` 下按功能分子目录
- `baseURL: 'http://localhost:5173'` — 指向 Vite dev server
- `webServer` — 自动运行 `npm run dev` 启动 Vite，CI 中不复用已有实例
- `trace: 'on-first-retry'` / `screenshot: 'only-on-failure'` — 失败时自动截图 + trace
- `fullyParallel: true` — 测试并行执行

**Mock 策略**：

所有 API 调用通过 `page.route()` 拦截，返回 mock 响应，无需真实后端运行：

```typescript
import { test, expect } from '@playwright/test';

const MOCK_LOGIN_RESPONSE = {
  access: 'mock-access-token-abc123',
  refresh: 'mock-refresh-token-xyz789',
  user: { id: '1', username: 'testuser', role: 'admin' },
};

test('login flow', async ({ page }) => {
  await page.route('**/api/v2/accounts/auth/login/', async (route) => {
    await route.fulfill({ json: MOCK_LOGIN_RESPONSE });
  });
  await page.goto('/login');
  await page.fill('[name="username"]', 'testuser');
  await page.fill('[name="password"]', 'testpass');
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/dashboard/);
});
```

**运行**：

```powershell
# 安装浏览器（首次）
npx playwright install chromium

# 运行全部 TS E2E
npx playwright test --config frontend/e2e/playwright.config.ts

# 运行单个文件
npx playwright test frontend/e2e/auth/login.spec.ts

# 带 UI 调试模式
npx playwright test --ui
```

## 5. 通用测试模式

### 5.1 Throttle 禁用（TD-068）

含集成测试（多次调登录）的 app，其 `tests/__init__.py` 必须清空登录节流类：

```python
# backend/<app>/tests/__init__.py
from accounts.views import CustomTokenObtainPairView

# TD-068: clear login-scoped throttle so ~30 login calls do not hit 5/min
CustomTokenObtainPairView.throttle_classes = []
```

### 5.2 JWT 认证流

测试中走真实登录获取 token，不用 `force_login` 绕过：

```python
resp = self.client.post("/api/v2/accounts/auth/login/",
                        {"username": "admin", "password": "admin123"}, format="json")
token = resp.json()["access"]
self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
```

### 5.3 Mock Celery .delay

见 §2.6。断言 `assert_called_once_with(...)`，不验证异步执行结果。

### 5.4 URL 枚举测试

见 §2.5。枚举 `urlpatterns` 防止路由误删。

### 5.5 权限矩阵测试

3 角色 × CRUD，至少测 viewer 写被拒（403）：

```python
@pytest.mark.parametrize("role,method,expected", [
    ("admin", "POST", 201),
    ("operator", "POST", 403),
    ("viewer", "POST", 403),
])
def test_create_permission(role, method, expected):
    ...
```

## 6. 覆盖率要求

| 层 | 工具 | 配置位置 | 阈值 |
|----|------|---------|------|
| 后端 | coverage.py | `pyproject.toml [tool.coverage.report]` | `fail_under = 30`（逐步提高） |
| 前端 | Vitest coverage | `vitest.config.ts` | lines=40, branches=30, functions=35, statements=40 |
| E2E | （不统计覆盖率） | — | 场景通过率 100% |

- 提交前必跑覆盖率（project_rules §3.4 大阶段提交流程）
- 覆盖率不达标 = commit 失败，必须补测试或调低基线（调低需登记 tech-debt）

## §7 agent 节点测试规范

### 7.1 节点关键方法单测覆盖 (N185)

agent 引擎节点的关键方法 (非 happy path) 必须有单测覆盖:
- `_get_image` / `_get_template` 等资源获取方法: 必须覆盖 fallback 路径 (context 空 / device 不可用 / capture 失败)
- `execute` 主方法: 必须覆盖 fail_result 路径 (返回 NodeResult.success=False)
- 坐标转换 / ROI 缩放: 必须覆盖边界情况 (分辨率不匹配 / 坐标越界)

### 7.2 节点观测性测试 (N184)

节点 fail_result 必须带观测性:
- logger.warning + exc_info=True
- 错误消息含上下游上下文 (输入参数 + 上游节点状态 + 失败原因)
- 禁止静默吞错 (except Exception 必须 logger.warning, 不能 pass)

### 7.3 agent chain e2e 测试 (N177)

agent chain e2e 测试纳入 N177 分级测试表 (见 project_rules §4.9):
- 小修改: 不要求
- 中修改: 不要求
- 大修改: 至少 1 个 chain e2e 冒烟测试 (首节点 → 末节点跑通)
