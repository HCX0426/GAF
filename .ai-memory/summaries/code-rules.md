---
date: 2026-01-01
maintainer: manual
symptom: [code-rules, coding, pitfalls, environment]
solution: 代码编写规则与工具使用约束 — 90+ 条历史错误汇总
diff_keywords: ["architecture", "mistakes", "architecture-mistakes", "library", "conflicts", "library-conflicts", "failure", "modes", "failure-modes", "code-rules", "coding", "pitfalls"]
related_files:
  - .ai-memory/summaries/architecture-mistakes.md
  - .ai-memory/summaries/library-conflicts.md
  - .ai-memory/meta/failure-modes.md
created_by: AI
priority: high
load_when: [on-demand]
source: handwritten
---


# AI Code Rules & Pitfalls

> **与 docs/standards/backend-conventions.md 边界**:
> - **本文件** = AI 工具规则 (怎么用工具) — SearchReplace/PowerShell/监控控制台/PS7 vs 5.1/临时文件组织
> - **backend-conventions.md** = 代码规范 (写什么代码) — Django/DRF 命名/序列化/权限/响应/测试
> - 两者互补不重叠; 改工具使用查本文件, 改代码规范查 backend-conventions.md

> **SUPPLEMENTARY: 工具规则补充参考 (L3 按需加载).**
> 本文件为工具规则补充参考,核心红线已迁至 `ai-operating-handbook.md` Part 2,AI 应以 handbook 为单一权威源。本文件仅保留 handbook 未覆盖的工具细节。
> Last updated: 2026-07-18 (TD-185 修复: §2.1 PS5 表述误导 + §2.1 PS7 兼容说明) | Source: gaf-v2-execution-charter.md reflections

---

## 1. Code Writing Rules

### 1.1 SearchReplace Safety
- **Never** use SearchReplace on `frontend source files` files with `old_str` > 5 lines
- SearchReplace corrupts `/**`, `_`, `[]`, `<>` into `/\*\*`, `\_`, `\[\]`, `\<\>`
- **CRITICAL: SearchReplace corrupts UTF-8 multibyte characters (CJK text) into `\ufffd` replacement chars**
  - Every SearchReplace on a file containing Chinese/Japanese/Korean text risks silent encoding corruption
  - Corruption is cumulative: each SearchReplace call may damage additional characters elsewhere
  - **Symptom**: Vite reports `[PARSE_ERROR] Unterminated string` with `?` in error output
  - **Recovery**: `git checkout -- <file>` to restore original, then use Write tool (not SearchReplace)
  - **Safe alternative**: For CJK files, use Python script to do targeted replacements via file read/write
- For large changes: use Write tool to rewrite entire file
- **Always verify** after editing: read first 5 lines, grep for `\\_\[` and `\\\*\\*` and `\ufffd`
- Never leave markdown code fence ```残留 in code

### 1.2 Variable/Field Consistency
- **Always** verify variable names are consistent across the same scope
- Mistake: `rechecked_inst` vs `refreshed_inst` in same loop → NameError
- Mistake: `select_related('resource_pack')` when FK field is `'game_account'`
- Mistake: accessing `r['status']` when API returns `r['new_status']`

### 1.3 Import Discipline
- **Always** include all required imports — never assume implicit availability
- Missing imports caused: 500 errors (timezone), SyntaxError (io module)
- **Verify** icon imports exist in current antd version before using
- Mistake: `TestOutlined` removed in @ant-design/icons 5.x → use `PlayCircleOutlined`
- Mistake: `CheckOutlined` removed → use `CheckCircleOutlined`

### 1.4 React/TypeScript Patterns
- **Never** use `useState(() => { ... })` to handle prop changes — use `useEffect`
- Always use `Array.isArray()` for API data, not `|| []` (objects are truthy)
- Always handle form `initialValues` with `useEffect` + `form.setFieldsValue` for edit mode
- PUT requests require ALL required fields — use PATCH if only updating partial
- Always use `antTheme.useToken()` for theme access, not undefined `isDark`

### 1.5 JSX/TSX Syntax
- **Never** use template literals inside JSX: `` `推荐: ${...}` `` → use `'推荐: ' + ...`
- **Never** place extra commas in JSX attributes
- TypeScript type annotations must use correct syntax: `'dark' }: T` not `'dark': T`

### 1.6 Database/Model Safety
- **Always** initialize variables before conditional branches (UnboundLocalError: proc_ok)
- Use `get_or_create` / `update_or_create` for first-time registration scenarios
- Never use `@staticmethod` when instance data isolation is needed

### 1.7 Layout/Rendering
- **Never** use `collapsible collapsedSize={0}` without proper default visibility
- `react-resizable-panels` `defaultSize` must be string percentages: `"15%"` not number `15`
- **Always** verify imports exist before committing — missing imports cause Vite white screen
- Form components inside conditional rendering lose `useForm` connection — lift Form outside conditional
- **Always** verify Sidebar menu items are synced when adding new pages — if App.tsx has a route but Sidebar doesn't have a menu item, the page is unreachable

---

## 2. Tool Usage Rules

### 2.1 Shell Commands (PowerShell 7 兼容 5.1 — TD-185 修复 2026-07-18)
- **默认 PS7 支持 `&&` / `||` 操作符**; 如需 PS5.1 兼容用 `;` 分隔 (见 §5 PS7 vs 5.1 差异表)
- PowerShell 7 也支持 `;` 链式执行 (与 PS5.1 一致), 推荐 `;` 用于跨版本兼容场景
- **Never** use multi-line `conda run -c "..."` — it throws `NotImplementedError` (PS7 + PS5.1 均不支持)
- Write Python code to temporary `.py` file, then execute: `conda run -n gaf python _temp.py`
- **Never** use `curl` — it's `Invoke-WebRequest` alias in PowerShell (PS7 + PS5.1 均如此)
- Use `Invoke-WebRequest -Uri "..." -Method GET -UseBasicParsing`
- Use `Invoke-RestMethod` for JSON responses
- **commit message 单行优先** (N170): 单行 `-m` 不弹窗; 多行 `-m` (多个 -m flag) 和 `-F <file>` 都弹窗 (Trae 风险判定)

### 2.2 Browser Testing (browser-use)
- React `onClick` may not trigger via browser-use — use JS eval: `element.click()`
- antd Select dropdown has limited coverage — combine JS eval for verification
- **Always** verify file creation after parallel task agents — don't assume files exist

### 2.3 Build/Dev Server
- **Always** clear Vite cache after structural changes: delete `node_modules/.vite`
- "Code changed but not taking effect" = Vite cache issue 90% of the time
- `ast.parse` success ≠ working code — must verify: import + instantiate + function call

### 2.4 File Creation
- **Never** use `Set-Content -Path` to create Python/JS files — corrupts f-strings and special characters
- **Always** use `Write` tool for file creation — preserves syntax integrity
- For quick verification: prefer `Grep` + `Read` over writing custom verification scripts

---

## 3. Environment Rules

### 3.1 Service Startup
- **Always** use `scripts/gaf_services.ps1` (N194, 2026-07-28): `start` / `stop` / `restart` / `status`
- Replaces legacy `start.bat` / `start.ps1` / `stop.bat` / `stop.sh` (all deleted)
- Ensures unique instance — kills stale processes on ports :6379/:8000/:5173 before start
- Verify Redis is running before Django/Celery (script handles this automatically)

### 3.2 Dependencies
- **Always** verify conda environment has required packages (`pip install psutil`)
- ADB may not be in system PATH — auto-discover common emulator paths
- Hardcoded registry paths fail when software installed on different drive — use process name detection first

### 3.3 Database State
- Window hwnd expires when window closes — always refresh before use
- Local Agent auto-registration needs `get_or_create` with `is_local=True`

### 3.4 Error Handling (CRITICAL — Phase R19)
- **NEVER** use `except Exception: pass` — this silently swallows errors and makes debugging impossible
- **ALWAYS** log exceptions with `logger.warning/error()` and include `exc_info=True` for stack traces
- **API endpoints** MUST return error information to frontend in response JSON:
  - Use `null` for unknown/failed values (not fake zeros)
  - Include `error` or `warning` field with error message string
  - Example: `{'success': False, 'error': 'Database connection failed: ...'}`
- **Fallback pattern**: When returning default values on error, always include error reason:
  ```python
  except Exception as e:
      logger.warning('Operation failed: %s', e, exc_info=True)
      return {'data': [], 'error': str(e)}  # Frontend can display this
  ```
- **WebSocket broadcasts**: Log failures but don't crash (non-critical path):
  ```python
  except Exception as e:
      logger.warning('Broadcast failed: %s', e, exc_info=True)
  ```
- **Performance-sensitive code** (e.g., window enum callbacks): Minimal logging OK, but never silent `pass`

### 3.5 Frontend Error Handling (CRITICAL — Phase R20)
- **NEVER** use empty `catch {}` or `catch { message.error('fixed string') }` — this masks network/auth/server errors
- **ALWAYS** use `classifyError()` from `frontend/src/utils/errorHandler.ts` for error classification in catch blocks
- **Login page errors MUST distinguish**:
  - Network/timeout → "无法连接到服务器，请检查后端是否启动"
  - Auth failure (401) → "用户名或密码错误"
  - Server error (500+) → "服务器内部错误：{detail}"
- **Auth store errors MUST include context**: Append operation name when rethrowing (e.g., "2FA 验证失败: ...")
- **Axios interceptors MUST log** refresh failures before redirect: `console.warn('[axios] ...')`
- **Pattern for catch blocks**:
  ```typescript
  } catch (err: unknown) {
    const classified = classifyError(err);
    if (classified.type === ErrorType.NETWORK || classified.type === ErrorType.TIMEOUT) {
      message.error('无法连接到服务器，请检查后端是否启动');
    } else if (classified.type === ErrorType.AUTH) {
      message.error('认证失败信息');
    } else {
      message.error(`操作失败：${classified.message}`);
    }
  }
  ```

### 3.6 File Corruption Prevention (CRITICAL — Phase R20-FIX Lesson)
- **NEVER** use `Set-Content` to write Python/JS/TS files — PowerShell 5 corrupts special characters (`_` → `\_`, `*` → `\*`, Chinese → mojibake)
- **ALWAYS** use the `Write` tool for creating/editing code files
- **After any bulk edit**, verify file syntax: `py_compile.compile(file, doraise=True)` for Python
- **After git commit**, spot-check committed files for escape sequences: `git diff --stat` + grep for `\\_`
- **If corruption is found**: Restore from last known good git version, then reapply changes using proper tools

### 3.7 File Organization (N125 + cache consolidation)
- **All dev/debug temp files → `.trash/`** — 临时脚本、截图、日志、测试产物 (N125)
- **All tool caches → `.cache/`** — pytest/mypy/ruff (configured in `pyproject.toml`)
- **`__pycache__/` is auto-managed** — Python bytecode, gitignored, no action needed
- **Run pytest/mypy/ruff from repo root** — `pyproject.toml` `cache_dir` is CWD-relative; running from `backend/` creates duplicate `backend/.cache/`, `backend/.pytest_cache/`, `backend/.mypy_cache/`
- **`cd backend` is safe for Django commands only** — `manage.py runserver`/`migrate` don't create tool caches
- **Full rules**: see `project_rules.md §1.5 测试注意事项 + 文件组织`

---

## 4. Verification Checklist

Before claiming any task is complete:

- [ ] SearchReplace damage check: grep `\\_\[` and `\\\*\\*` in edited .tsx/.ts files
- [ ] All imports verified: no missing module errors
- [ ] Variable names consistent across scope
- [ ] API data access uses `Array.isArray()` defense
- [ ] Form edit mode uses `useEffect` + `setFieldsValue`
- [ ] Vite cache cleared if structural changes made
- [ ] Services running (use `scripts/gaf_services.ps1 status`)
- [ ] Browser console: zero JS errors
- [ ] All interactive elements tested (buttons, tabs, switches, selects, modals)

## 5. 默认终端 (PowerShell 7.x — 强制)

- **默认终端**: PowerShell 7.x（`pwsh.exe`，非 Windows PowerShell 5.1）
- **版本**: 7.6.2（通过 Microsoft Store 安装）
- **路径**: `C:\Users\hcx\AppData\Local\Microsoft\WindowsApps\pwsh.exe`
- **Windows Terminal**: 已设为系统默认终端应用，PowerShell 7 为默认 profile
- **Trae IDE 终端**: 已配置为 PowerShell 7（见 `Trae CN/User/settings.json`）
- **PowerShell 7 vs 5.1 差异**:
  - ✅ PS7 支持 `&&` / `||` 操作符（PS5.1 不支持）
  - ✅ PS7 支持三元运算符 `$cond ? $a : $b`（PS5.1 不支持）
  - ✅ PS7 支持并行 `ForEach-Object -Parallel`（PS5.1 不支持）
  - ❌ PS7 仍不支持 heredoc `<<'EOF'`（用 `@'...'@` here-string 替代）
  - ❌ PS7 仍不支持 `conda run -c "多行脚本"`（写临时 .py 文件替代）
- **开源 Skill 参考**:
  - `~/.trae-cn/skills/powershell-windows/SKILL.md` — PowerShell 用法指南
  - `~/.trae-cn/skills/git-automation/SKILL.md` — Git 操作指南

## 6. 监控控制台（强制 — 用户反馈 2026-07-14）

> **来源**：用户反馈 "以后打开 GAF 界面时我都要你打开监控控制台的脚本，你自己监控，然后可以定时读取日志，或者在我关闭后读取，这是你要监控的，有问题就记录，转为常驻操作，沉淀下"

**硬约束**：
- ✅ **打开 GAF 界面时必启动 `scripts/e2e/scenarios/console_monitor.py`** — 用户要求"打开界面" = 启动有头浏览器 + 全量 console 监听；不得用简单 `open_dashboard.py` 替代
- ✅ **AI 定时读取日志** — 监控启动后，AI 每 2-5 分钟 `Read .trash/console_monitor.log` 检查新输出；或用户关闭浏览器后立即读取
- ✅ **有问题就记录** — 发现 `[ERROR]` / `[PAGE_ERROR]` / `[REQFAIL]` 立即登记到 `docs/archive/active-tech-debt.md`（如属代码 bug）或 `.ai-memory/lessons/`（如属可复现经验）
- ✅ **常驻操作** — 监控脚本作为 long_running_process 后台运行，AI 通过 `CheckCommandStatus` 轮询；用户关闭浏览器 → 脚本自动退出 → AI 读取最终日志
- ❌ **禁止裸打开浏览器不监控** — 直接 `OpenPreview` 或简单登录脚本无法捕获 console 错误，违反"打开界面必监控"约束

**启动命令**（long_running_process，后台运行）：
```powershell
conda run -n gaf python scripts/e2e/scenarios/console_monitor.py
```

**监控覆盖**（由 `console_monitor.py` 自动捕获）：
- `[ERROR]` / `[WARNING]` / `[INFO]` / `[DEBUG]` — 所有 console 消息
- `[PAGE_ERROR]` — 未捕获异常
- `[REQFAIL]` — 失败的网络请求
- `[NAV]` — 页面导航
- `[CLICK]` — 用户点击目标（注入 document-level listener）

**日志位置**：`.trash/console_monitor.log`（gitignored，每次启动覆盖）

**AI 监控节奏**：
1. 启动后 wait 10-15s 让浏览器登录完成
2. 每 2-5 分钟 `Read .trash/console_monitor.log` 检查新错误
3. 用户关闭浏览器后 `CheckCommandStatus` 确认脚本退出，读取最终日志
4. 发现错误 → 分类（bug / 可复现经验 / 一次性事件）→ 登记到对应文件
