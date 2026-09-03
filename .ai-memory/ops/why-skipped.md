# e2e why-skipped 失败记录

> 本文件记录 e2e 场景失败 (scenario, detail, 修复路径, 优先级), 用于 M2.E 闭环。
> **TD-306 dedup 机制 (2026-07-21, spec-72)**: 同 scenario 在 `WHY_SKIPPED_DEDUP_HOURS` (默认 24h) 内只记录 1 次, 避免环境问题 (服务未启动/索引未生成) 重复刷屏。
> 写入逻辑见 `scripts/e2e/run_all.py:_write_why_skipped`, dedup 解析见 `_recent_why_skipped_scenarios`。
> 历史记录 (2026-06-17 ~ 2026-07-20, 233 行) 已在 spec-72 清理 — 全部为环境问题重复 (cold_start/browser_login/devices_control_mode/ai_qa_chat), 无代码 bug 需转 lessons/。


## e2e 失败记录 @ 2026-07-21 19:45:12

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `cold_start` | cold_start missing ['agent-protocol.md', 'api-endpoints.md', 'error-codes.md', 'pipeline-nodes.md'] | 查 N91 映射表 → gaf-session-check (python scripts/bootstrap/check_session_active.py --create) + 跑 gaf_init.sh | P0 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-07-21 19:45:27

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `browser_login` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\browser_login.py", line 50, in run_browser_login     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查前后端服务是否启动 + Playwright/Chromium 是否安装 (pyproject.toml dev deps) | P2 |
| `devices_control_mode` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\devices_control_mode.py", line 51, in run_devices_control_mode     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查 /devices/windows 页面 + control-mode 选择器渲染 (TD-015) | P2 |
| `ai_qa_chat` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\ai_qa_chat.py", line 60, in run_ai_qa_chat     page.goto(frontend_url, wait_until="domcontentloaded", timeout=15000)   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"   | 查 LLMConfig 是否配置 + SiliconFlow API key + /qa/ask/ 端点 (commit - 回归) | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-07-22 22:22:01

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `cold_start` | cold_start missing ['agent-protocol.md', 'api-endpoints.md', 'error-codes.md', 'pipeline-nodes.md'] | 查 N91 映射表 → gaf-session-check (python scripts/bootstrap/check_session_active.py --create) + 跑 gaf_init.sh | P0 |
| `browser_login` | console errors: ['[error] Warning: [antd: Space] `direction` is deprecated. Please use `orientation` instead.'] | 查前后端服务是否启动 + Playwright/Chromium 是否安装 (pyproject.toml dev deps) | P2 |
| `devices_control_mode` | console errors: ['[error] Warning: [antd: Space] `direction` is deprecated. Please use `orientation` instead.', '[error] Warning: [antd: Space] `direction` is deprecated. Please use `orientation` instead.'] | 查 /devices/windows 页面 + control-mode 选择器渲染 (TD-015) | P2 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-07-26 21:48:12

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `cold_start` | cold_start missing ['agent-protocol.md', 'api-endpoints.md', 'cli-cheatsheet.md', 'data-flow.md', 'error-codes.md', 'pipeline-nodes.md', 'tech-stack.md', 'version-compat.md'] | 查 N91 映射表 → gaf-session-check (python scripts/bootstrap/check_session_active.py --create) + 跑 gaf_init.sh | P0 |
| `bug_fix` | bug_fix: N118 lesson file missing (expected *2026-06-17-n118*) | 查 N91 映射表 + gaf-reflect-and-evolve §3.2 → 写 lesson + arch + failure-modes 5 层分发 | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-07-26 21:48:24

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `browser_login` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\browser_login.py", line 50, in run_browser_login     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查前后端服务是否启动 + Playwright/Chromium 是否安装 (pyproject.toml dev deps) | P2 |
| `devices_control_mode` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\devices_control_mode.py", line 51, in run_devices_control_mode     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查 /devices/windows 页面 + control-mode 选择器渲染 (TD-015) | P2 |
| `ai_qa_chat` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\ai_qa_chat.py", line 60, in run_ai_qa_chat     page.goto(frontend_url, wait_until="domcontentloaded", timeout=15000)   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"   | 查 LLMConfig 是否配置 + SiliconFlow API key + /qa/ask/ 端点 (commit - 回归) | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-07-30 22:54:26

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `cold_start` | cold_start missing ['agent-protocol.md', 'api-endpoints.md', 'cli-cheatsheet.md', 'data-flow.md', 'error-codes.md', 'pipeline-nodes.md', 'tech-stack.md', 'version-compat.md'] | 查 N91 映射表 → gaf-session-check (python scripts/bootstrap/check_session_active.py --create) + 跑 gaf_init.sh | P0 |
| `bug_fix` | bug_fix: N118 lesson file missing (expected *2026-06-17-n118*) | 查 N91 映射表 + gaf-reflect-and-evolve §3.2 → 写 lesson + arch + failure-modes 5 层分发 | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-07-30 22:54:41

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `browser_login` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\browser_login.py", line 50, in run_browser_login     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查前后端服务是否启动 + Playwright/Chromium 是否安装 (pyproject.toml dev deps) | P2 |
| `devices_control_mode` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\devices_control_mode.py", line 51, in run_devices_control_mode     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查 /devices/windows 页面 + control-mode 选择器渲染 (TD-015) | P2 |
| `ai_qa_chat` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\ai_qa_chat.py", line 60, in run_ai_qa_chat     page.goto(frontend_url, wait_until="domcontentloaded", timeout=15000)   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"   | 查 LLMConfig 是否配置 + SiliconFlow API key + /qa/ask/ 端点 (commit - 回归) | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-08-08 19:57:35

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `cold_start` | cold_start missing ['agent-protocol.md', 'api-endpoints.md', 'cli-cheatsheet.md', 'data-flow.md', 'error-codes.md', 'pipeline-nodes.md', 'tech-stack.md', 'version-compat.md'] | 查 N91 映射表 → gaf-session-check (python scripts/bootstrap/check_session_active.py --create) + 跑 gaf_init.sh | P0 |
| `bug_fix` | bug_fix: N118 lesson file missing (expected *2026-06-17-n118*) | 查 N91 映射表 + gaf-reflect-and-evolve §3.2 → 写 lesson + arch + failure-modes 5 层分发 | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-08-08 19:57:51

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `browser_login` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\browser_login.py", line 51, in run_browser_login     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查前后端服务是否启动 + Playwright/Chromium 是否安装 (pyproject.toml dev deps) | P2 |
| `devices_control_mode` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\devices_control_mode.py", line 52, in run_devices_control_mode     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查 /devices/windows 页面 + control-mode 选择器渲染 (TD-015) | P2 |
| `ai_qa_chat` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\ai_qa_chat.py", line 62, in run_ai_qa_chat     page.goto(frontend_url, wait_until="domcontentloaded", timeout=15000)   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"   | 查 LLMConfig 是否配置 + SiliconFlow API key + /qa/ask/ 端点 (commit - 回归) | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-08-17 21:28:57

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `browser_login` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\browser_login.py", line 51, in run_browser_login     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查前后端服务是否启动 + Playwright/Chromium 是否安装 (pyproject.toml dev deps) | P2 |
| `devices_control_mode` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\devices_control_mode.py", line 52, in run_devices_control_mode     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查 /devices/windows 页面 + control-mode 选择器渲染 (TD-015) | P2 |
| `ai_qa_chat` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\ai_qa_chat.py", line 62, in run_ai_qa_chat     page.goto(frontend_url, wait_until="domcontentloaded", timeout=15000)   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"   | 查 LLMConfig 是否配置 + SiliconFlow API key + /qa/ask/ 端点 (commit - 回归) | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-08-18 21:43:14

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `browser_login` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\browser_login.py", line 51, in run_browser_login     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查前后端服务是否启动 + Playwright/Chromium 是否安装 (pyproject.toml dev deps) | P2 |
| `devices_control_mode` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\devices_control_mode.py", line 52, in run_devices_control_mode     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查 /devices/windows 页面 + control-mode 选择器渲染 (TD-015) | P2 |
| `ai_qa_chat` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\ai_qa_chat.py", line 62, in run_ai_qa_chat     page.goto(frontend_url, wait_until="domcontentloaded", timeout=15000)   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"   | 查 LLMConfig 是否配置 + SiliconFlow API key + /qa/ask/ 端点 (commit - 回归) | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-08-20 20:33:55

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `cross_repo` | cross_repo: policy '不可逆数据删除' missing in project_rules | 查 project_rules §3.6 N109 → 3 类需授权 (跨工作区/重写 history/不可逆删除) | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-08-20 20:34:08

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `browser_login` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\browser_login.py", line 51, in run_browser_login     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查前后端服务是否启动 + Playwright/Chromium 是否安装 (pyproject.toml dev deps) | P2 |
| `devices_control_mode` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\devices_control_mode.py", line 52, in run_devices_control_mode     page.goto(f"{frontend_url}/login", wait_until="networkidle")   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/login Call log:   - navigating to "http://127.0.0.1:5173/login", waiting until "networkidle"   | 查 /devices/windows 页面 + control-mode 选择器渲染 (TD-015) | P2 |
| `ai_qa_chat` | browser automation failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"  Traceback (most recent call last):   File "D:\code\GAF\scripts\e2e\scenarios\ai_qa_chat.py", line 62, in run_ai_qa_chat     page.goto(frontend_url, wait_until="domcontentloaded", timeout=15000)   File "D:\code\environment\conda\envs\gaf\Lib\site-packages\playwright\sync_api\_generated.py", line 9612, in goto     self._sync( playwright._impl._errors.Error: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:5173/ Call log:   - navigating to "http://127.0.0.1:5173/", waiting until "domcontentloaded"   | 查 LLMConfig 是否配置 + SiliconFlow API key + /qa/ask/ 端点 (commit - 回归) | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-08-28 15:36:59

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `full_routes` | full_routes: 40 PASS / 0 WARN / 1 FAIL / 6 SKIP (47 routes) PASS  /login                                 [A-01/02/03]  PASS  /setup                                 [A-04]  PASS  /dashboard                             [B-01/02/03]  PASS  /game-profiles                         [C-01/02/03]  PASS  /tasks                                 [D-01/02]  PASS  /tasks/pipeline                        [D-05/06]  PASS  /tasks/recordings                      [D-09]  PASS  /tasks/marketplace                     [D-10]  PASS  /devices                               [E-01/04/08]  PASS  /devices/emulators                     [E-05]  PASS  /devices/windows                       [E-06]  FAIL  /devices/adb-logs                      [E-07] console error: WebSocket connection to 'ws://127.0.0.1:5173/ws/devices/1/adb-logs/?' failed: Error during WebSocket handshake: Sent non-empty 'Sec-WebSocket-Protocol' header b PASS  /resources                             [F-01/02]  PASS  /resources/template-effectiveness      [F-03]  PASS  /resources/annotation                  [F-04/05/06]  PASS  /accounts/users                        [G-01]  PASS  /accounts/game-accounts                [G-02/03/04]  PASS  /ops/unattended                        [H-01/02]  PASS  /ops/executions                        [H-03/04]  PASS  /ops/scheduler                         [H-07]  PASS  /ops/scheduler/dag                     [H-08]  PASS  /ops/monitors                          [H-09/10]  PASS  /ops/analytics                         [H-11]  PASS  /ops/sla                               [H-12]  PASS  /ops/logs                              [H-13]  PASS  /ai/assistant                          [I-01/02]  PASS  /ai/qa                                 [I-03]  PASS  /ai/anomaly                            [I-04]  PASS  /ai/skill-editor                       [I-05]  PASS  /ai/skill-market                       [I-06]  PASS  /ai/log-analysis                       [I-07]  PASS  /ai/config                             [I-08]  PASS  /ai/usage                              [I-09]  PASS  /system/settings                       [J-01/02/03/04]  PASS  /system/config                         [J-05]  PASS  /system/api-keys                       [J-06]  PASS  /system/backup                         [J-07]  PASS  /system/feature-flags                  [J-08]  PASS  /system/audit-log                      [J-09]  PASS  /system/notifications                  [J-10]  PASS  /system/plugins                        [J-11]  SKIP  /game-profiles/{id}                    [C-04/05/06] no env data for probe /gamestate/game-profiles/ SKIP  /tasks/{id}/edit                       [D-03/04] no env data for probe /tasks/ SKIP  /tasks/pipeline/{id}                   [D-08] no env data for probe /pipeline/pipelines/ SKIP  /devices/adb-logs/{id}                 [E-07] no env data for probe /devices/ SKIP  /ops/scheduler/dag/{id}                [H-08] no env data for probe /pipeline/task-chains/ SKIP  /ops/executions/{id}/replay            [H-03] no env data for probe /tasks/task-executions/ | 逐路由查 docs/health/e2e-test-plan.md 对应用例 → 页面崩溃/未渲染/console error 均登记 docs/health/e2e-coverage.md 问题表; 先确认 backend:8000 + frontend:5173 正常 | P2 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-08-28 18:35:09

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `bug_fix` | bug_fix: N118 reference missing in arch or failure-modes | 查 N91 映射表 + gaf-reflect-and-evolve §3.2 → 写 lesson + arch + failure-modes 5 层分发 | P1 |
| `cross_repo` | cross_repo: policy '跨工作区' missing in project_rules | 查 project_rules §3.6 N109 → 3 类需授权 (跨工作区/重写 history/不可逆删除) | P1 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---

## e2e 失败记录 @ 2026-09-03 18:31:36

| scenario | detail | 修复路径 | 优先 |
|----------|--------|----------|:----:|
| `browser_login` | console errors: ["[error] Warning: Form already set 'initialValues' with path 'remember_me'. Field can not overwrite it."] | 查前后端服务是否启动 + Playwright/Chromium 是否安装 (pyproject.toml dev deps) | P2 |
| `devices_control_mode` | console errors: ["[error] Warning: Form already set 'initialValues' with path 'remember_me'. Field can not overwrite it."] | 查 /devices/windows 页面 + control-mode 选择器渲染 (TD-015) | P2 |
| `full_routes` | full_routes: 43 PASS / 0 WARN / 5 FAIL / 0 SKIP (48 routes) FAIL  /login                                 [A-01/02/03] console error: Warning: Form already set 'initialValues' with path 'remember_me'. Field can not overwrite it. FAIL  /setup                                 [A-04] console error: Warning: Form already set 'initialValues' with path 'remember_me'. Field can not overwrite it. PASS  /dashboard                             [B-01/02/03]  PASS  /game-profiles                         [C-01/02/03]  PASS  /tasks                                 [D-01/02]  PASS  /tasks/pipeline                        [D-05/06]  PASS  /tasks/recordings                      [D-09]  PASS  /tasks/marketplace                     [D-10]  PASS  /devices                               [E-01/04/08]  PASS  /devices/emulators                     [E-05]  PASS  /devices/windows                       [E-06]  PASS  /devices/adb-logs                      [E-07]  PASS  /resources                             [F-01/02]  PASS  /resources/template-effectiveness      [F-03]  PASS  /resources/annotation                  [F-04/05/06]  PASS  /accounts/users                        [G-01]  PASS  /accounts/game-accounts                [G-02/03/04]  PASS  /ops/unattended                        [H-01/02]  PASS  /ops/executions                        [H-03/04]  PASS  /ops/scheduler                         [H-07]  PASS  /ops/scheduler/dag                     [H-08]  PASS  /ops/monitors                          [H-09/10]  FAIL  /ops/analytics                         [H-11] console error: Failed to load resource: the server responded with a status of 500 (Internal Server Error) PASS  /ops/sla                               [H-12]  PASS  /ops/logs                              [H-13]  FAIL  /ai/assistant                          [I-01/02] unexpected url: http://127.0.0.1:5173/dashboard PASS  /ai/qa                                 [I-03]  FAIL  /ai/anomaly                            [I-04] unexpected url: http://127.0.0.1:5173/dashboard PASS  /ai/skill-editor                       [I-05]  PASS  /ai/skill-market                       [I-06]  PASS  /ai/log-analysis                       [I-07]  PASS  /ai/config                             [I-08]  PASS  /ai/usage                              [I-09]  PASS  /system/settings                       [J-01/02/03/04]  PASS  /system/config                         [J-05]  PASS  /system/api-keys                       [J-06]  PASS  /system/backup                         [J-07]  PASS  /system/feature-flags                  [J-08]  PASS  /system/audit-log                      [J-09]  PASS  /system/services                       [J-10]  PASS  /system/notifications                  [J-11]  PASS  /system/plugins                        [J-12]  PASS  /game-profiles/7                       [C-04/05/06]  PASS  /tasks/25/edit                         [D-03/04]  PASS  /tasks/pipeline/2                      [D-08]  PASS  /devices/adb-logs/14                   [E-07]  PASS  /ops/scheduler/dag/6                   [H-08]  PASS  /ops/executions/100/replay             [H-03]     4xx/5xx (up to 5):      500 http://127.0.0.1:5173/api/v2/analytics/step-heatmap/ | 逐路由查 docs/health/e2e-test-plan.md 对应用例 → 页面崩溃/未渲染/console error 均登记 docs/health/e2e-coverage.md 问题表; 先确认 backend:8000 + frontend:5173 正常 | P2 |

> 下一步: 跑 `python scripts/lessons/weekly_summary.py` 汇总本周失败 + 提议转 lessons/失败模式。

---
