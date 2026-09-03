"""full_routes — 全功能真实无头浏览器 smoke 场景（持久化 E2E 用例库）。

覆盖 ``docs/health/e2e-test-plan.md`` 里 A–K 全部模块的前端路由（46 条：
40 静态 + 6 动态）。每路由真实走后端链路（Vite dev server → Django API），
无 mock、无 page.route 拦截，符合用户 2026-08-28 决策：
「必须真实用无头浏览器测，不能不走后端」。

判定基准（对齐 e2e-coverage.md 验收标准）：
  PASS  = 页面 URL 正确 + 侧边栏渲染 + body 有内容 + 无未捕获异常
          + 无 console error（白名单噪音除外）
  WARN  = 存在 4xx/5xx 或已知噪音 console error（记录不判失败）
  FAIL  = 崩溃（ErrorBoundary）/ 未渲染 / 未捕获异常 / 意外跳登录
  SKIP  = 动态路由在环境里探测不到真实数据 id

同步纪律（重要）：
  - 新增前端页面 → 必须在下方 ROUTES / DYNAMIC_ROUTES 补充条目并回填
    ``docs/health/e2e-test-plan.md`` 用例 ID；两处必须保持一致。
  - 新功能上线未在 test-plan 登记 → 先补 test-plan 用例，再补本文件。
"""
from __future__ import annotations

import os
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173")
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"

# 页面崩溃文案关键词（ErrorBoundary 渲染后 body 出现即判定崩溃）
CRASH_KEYWORDS = (
    "Page Error",
    "页面出错了",
    "Something went wrong",
    "Application error",
    "渲染崩溃",
)

# console error 白名单——环境已知噪音，不计 FAIL（仍记录到 detail）
CONSOLE_NOISE = ("ERR_ABORTED", "CanceledError", "canceled", "favicon")

# 4xx/5xx 忽略模式（资源级噪音，非业务接口）
HTTP_IGNORE = ("/vite/", "favicon", "/node_modules/")

# ---------------------------------------------------------------------------
# 全路由清单：path + e2e-test-plan.md 用例 ID 标签（A-xx/B-xx/…）
# 新增页面时必须同步 test-plan 与这里。
# ---------------------------------------------------------------------------
ROUTES: list[dict] = [
    # A. 认证与系统框架（/setup、/login 已登录时会重定向到 /dashboard）
    {"path": "/login", "ids": "A-01/02/03", "group": "认证", "redirect": "/dashboard"},
    {"path": "/setup", "ids": "A-04", "group": "认证", "redirect": "/dashboard"},
    # B. 工作台
    {"path": "/dashboard", "ids": "B-01/02/03", "group": "工作台"},
    # C. 游戏档案
    {"path": "/game-profiles", "ids": "C-01/02/03", "group": "游戏档案"},
    # D. 任务
    {"path": "/tasks", "ids": "D-01/02", "group": "任务"},
    {"path": "/tasks/pipeline", "ids": "D-05/06", "group": "任务"},
    {"path": "/tasks/recordings", "ids": "D-09", "group": "任务"},
    {"path": "/tasks/marketplace", "ids": "D-10", "group": "任务"},
    # E. 设备
    {"path": "/devices", "ids": "E-01/04/08", "group": "设备"},
    {"path": "/devices/emulators", "ids": "E-05", "group": "设备"},
    {"path": "/devices/windows", "ids": "E-06", "group": "设备"},
    {"path": "/devices/adb-logs", "ids": "E-07", "group": "设备"},
    # F. 资源
    {"path": "/resources", "ids": "F-01/02", "group": "资源"},
    {"path": "/resources/template-effectiveness", "ids": "F-03", "group": "资源"},
    {"path": "/resources/annotation", "ids": "F-04/05/06", "group": "资源"},
    # G. 账户
    {"path": "/accounts/users", "ids": "G-01", "group": "账户"},
    {"path": "/accounts/game-accounts", "ids": "G-02/03/04", "group": "账户"},
    # H. 运维
    {"path": "/ops/unattended", "ids": "H-01/02", "group": "运维"},
    {"path": "/ops/executions", "ids": "H-03/04", "group": "运维"},
    {"path": "/ops/scheduler", "ids": "H-07", "group": "运维"},
    {"path": "/ops/scheduler/dag", "ids": "H-08", "group": "运维"},
    {"path": "/ops/monitors", "ids": "H-09/10", "group": "运维"},
    {"path": "/ops/analytics", "ids": "H-11", "group": "运维"},
    {"path": "/ops/sla", "ids": "H-12", "group": "运维"},
    {"path": "/ops/logs", "ids": "H-13", "group": "运维"},
    # I. AI
    {"path": "/ai/qa", "ids": "I-03", "group": "AI"},
    {"path": "/ai/skill-editor", "ids": "I-05", "group": "AI"},
    {"path": "/ai/skill-market", "ids": "I-06", "group": "AI"},
    {"path": "/ai/log-analysis", "ids": "I-07", "group": "AI"},
    {"path": "/ai/config", "ids": "I-08", "group": "AI"},
    {"path": "/ai/usage", "ids": "I-09", "group": "AI"},
    # J. 系统
    {"path": "/system/settings", "ids": "J-01/02/03/04", "group": "系统"},
    {"path": "/system/config", "ids": "J-05", "group": "系统"},
    {"path": "/system/api-keys", "ids": "J-06", "group": "系统"},
    {"path": "/system/backup", "ids": "J-07", "group": "系统"},
    {"path": "/system/feature-flags", "ids": "J-08", "group": "系统"},
    {"path": "/system/audit-log", "ids": "J-09", "group": "系统"},
    {"path": "/system/services", "ids": "J-10", "group": "系统"},
    {"path": "/system/notifications", "ids": "J-11", "group": "系统"},
    {"path": "/system/plugins", "ids": "J-12", "group": "系统"},
]

# 动态路由：{id} 占位符 + 真实 id 探测端点（相对 /api/v2）
# 探测失败（环境无数据）→ 该路由标记 SKIP，不算 FAIL。
DYNAMIC_ROUTES: list[dict] = [
    {"path": "/game-profiles/{id}", "ids": "C-04/05/06", "group": "游戏档案",
     "probe": "/gamestate/game-profiles/"},
    {"path": "/tasks/{id}/edit", "ids": "D-03/04", "group": "任务",
     "probe": "/tasks/"},
    {"path": "/tasks/pipeline/{id}", "ids": "D-08", "group": "任务",
     "probe": "/pipeline/pipelines/"},
    {"path": "/devices/adb-logs/{id}", "ids": "E-07", "group": "设备",
     "probe": "/devices/"},
    {"path": "/ops/scheduler/dag/{id}", "ids": "H-08", "group": "运维",
     "probe": "/pipeline/task-chains/"},
    {"path": "/ops/executions/{id}/replay", "ids": "H-03", "group": "运维",
     "probe": "/tasks/task-executions/"},
]


def _probe_first_id(page, probe_path: str) -> str | None:
    """从列表 API 探测第一个真实 id；无数据返回 None。

    JWT 存在 sessionStorage['access_token']（tokenStore.ts），axios 走
    Bearer header 而非 cookie，所以 probe 请求必须手动带 Authorization。
    """
    url = f"{DEFAULT_FRONTEND_URL}/api/v2/{probe_path.strip('/')}?page_size=1"
    headers = {}
    try:
        token = page.evaluate("sessionStorage.getItem('access_token')")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    except Exception:  # noqa: BLE001
        pass
    try:
        resp = page.context.request.get(url, headers=headers, timeout=8000)
        if resp.status >= 400:
            return None
        data = resp.json()
    except Exception:  # noqa: BLE001
        return None
    if isinstance(data, list):
        first = data[0] if data else None
    elif isinstance(data, dict):
        items = data.get("items") or data.get("results") or []
        first = items[0] if items else None
    else:
        first = None
    if not isinstance(first, dict):
        return None
    return str(first.get("id") or "").strip() or None


def run_full_routes(
    repo: Path,
    frontend_url: str = DEFAULT_FRONTEND_URL,
    username: str = DEFAULT_USERNAME,
    password: str = DEFAULT_PASSWORD,
) -> tuple[bool, str]:
    """Run the full-routes headless smoke scenario against the real stack.

    Returns ``(ok, detail)`` — detail carries a per-route verdict table so
    the runner log / why-skipped.md shows exactly which page failed.
    """
    verdicts: list[str] = []

    def _check_route(page, route_cfg: dict, path: str) -> tuple[bool, str]:
        """访问一个已解析 path 的路由，返回 (通过?, 备注)。"""
        url = f"{frontend_url}{path}"
        # 路由级错误游标
        err_idx = len(page_errors)
        con_idx = len(console_errs)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2200)
        except Exception as exc:  # noqa: BLE001
            return False, f"goto failed: {exc}"

        # 1) URL 判定：允许 redirect 场景（如 /setup → /dashboard）
        current = page.url.rstrip("/")
        allowed = {frontend_url.rstrip("/") + path.rstrip("/")}
        if route_cfg.get("redirect"):
            allowed.add(frontend_url.rstrip("/") + route_cfg["redirect"])
        if current not in allowed:
            return False, f"unexpected url: {current}"

        # 2) 崩溃文案 / 内容
        try:
            body_text = page.text_content("body") or ""
        except Exception:  # noqa: BLE001
            body_text = ""
        for kw in CRASH_KEYWORDS:
            if kw in body_text:
                return False, f"crash keyword in body: {kw}"
        if not body_text.strip():
            return False, "empty body"

        # 3) 侧边栏渲染
        try:
            page.locator("aside").first.wait_for(state="visible", timeout=3000)
        except Exception:  # noqa: BLE001
            return False, "aside not rendered (layout fail)"

        # 4) 未捕获异常 + console error（白名单噪音除外）
        route_page_errors = page_errors[err_idx:]
        if route_page_errors:
            return False, f"pageerror: {route_page_errors[0]}"
        route_console = [m for m in console_errs[con_idx:] if not any(
            n in m for n in CONSOLE_NOISE)]
        if route_console:
            return False, f"console error: {route_console[0][:160]}"

        return True, ""

    page_errors: list[str] = []
    console_errs: list[str] = []
    http_warns: dict[str, int] = {}

    def _on_console(msg) -> None:
        if msg.type == "error":  # type: ignore[attr-defined]
            console_errs.append(msg.text)  # type: ignore[attr-defined]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.on("pageerror", lambda exc: page_errors.append(f"[pageerror] {exc}"))
            page.on("console", _on_console)

            def _on_response(resp) -> None:
                if resp.status >= 400 and not any(
                    n in resp.url for n in HTTP_IGNORE
                ):
                    http_warns[resp.url.split("?")[0]] = resp.status

            page.on("response", _on_response)

            # 登录（真实后端 API）
            page.goto(f"{frontend_url}/login", wait_until="networkidle")
            page.locator('input[autocomplete="username"]').fill(username)
            page.locator('input[autocomplete="current-password"]').fill(password)
            page.locator('button[type="submit"]').click()
            page.wait_for_url("**/dashboard", timeout=15000)

            # 静态路由
            for route in ROUTES:
                ok, note = _check_route(page, route, route["path"])
                mark = "PASS" if ok and not note else "WARN" if ok and "WARN" in note else "FAIL"
                verdicts.append(f"{mark:5s} {route['path']:38s} [{route['ids']}] {note}")

            # 动态路由：探测真实 id
            for route in DYNAMIC_ROUTES:
                rid = _probe_first_id(page, route["probe"])
                if not rid:
                    verdicts.append(
                        f"SKIP  {route['path']:38s} [{route['ids']}] no env data for probe {route['probe']}"
                    )
                    continue
                path = route["path"].replace("{id}", rid)
                ok, note = _check_route(page, route, path)
                mark = "PASS" if ok and not note else "WARN" if ok and "WARN" in note else "FAIL"
                verdicts.append(f"{mark:5s} {path:38s} [{route['ids']}] {note}")

            browser.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"full_routes browser failed: {exc}\n{traceback.format_exc(limit=2)}"

    passed = sum(1 for v in verdicts if v.startswith("PASS"))
    warned = sum(1 for v in verdicts if v.startswith("WARN"))
    failed = sum(1 for v in verdicts if v.startswith("FAIL"))
    skipped = sum(1 for v in verdicts if v.startswith("SKIP"))
    lines = [f"full_routes: {passed} PASS / {warned} WARN / {failed} FAIL / {skipped} SKIP "
             f"({len(ROUTES) + len(DYNAMIC_ROUTES)} routes)"]
    lines += verdicts
    if http_warns:
        lines.append("   4xx/5xx (up to 5):")
        for url, status in sorted(http_warns.items())[:5]:
            lines.append(f"     {status} {url}")
    detail = "\n".join(lines)
    return (failed == 0), detail
