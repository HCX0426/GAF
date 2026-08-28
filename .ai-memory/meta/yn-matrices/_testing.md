---
summary: 测试套件环境依赖 Y/N 矩阵 — 环境依赖/命令卡死/复制粘贴重命名/认证图片blob/Python import遗漏/实机测试流程
applies_to: [test-environment, copy-paste, auth-image, python-import, reflection, real-device-test]
last_updated: 2026-08-17
source: Split from yn-matrices.md (Phase 4 Task 4.2)
---

## §6 testing — 测试套件环境依赖

## evidence_source 总览 (Wave 2 — 2026-07-26, spec-2026-07-26-ai-governance-execution-rate-fix)

> 每项 Y/N 检查的真实执行 evidence 来源 (hook 名 / spec 字段 / pytest 输出). 满足 Wave 2 验收 "保留 3 sub-file, 每项含 evidence_source 字段".

| N## | evidence_source | 验证方式 |
|-----|-----------------|---------|
| N118 (测试套件环境依赖) | `scripts/tests/test_gaf_commit_wrapper.py` (_find_bash) + `test_session_active.py` (binding hash) + `scripts/tests/run_all.py` (explicit module list) | `pytest scripts/tests/test_gaf_commit_wrapper.py scripts/tests/test_session_active.py` |
| N119 (命令卡死, 无独立 Y/N 矩阵) | `project_rules.md §5.9` 88 行 N119 4 原则 + 档位表 + `failure-modes.md N119` | grep `N119` .skills/rules/project_rules.md |
| N142 (复制-粘贴重命名) | `verify_r37_p1_playwright.py` Playwright 全 4 页烟测 + grep 旧名残留 | `grep -n "<OldName>" <NewFile>` 应 0 结果 |
| N143 (认证图片 blob) | `frontend/src/api/client.ts` axios baseURL + `revokeObjectURL` cleanup + `verify_r37_p1_playwright.py` failed responses = [] | grep `responseType.*blob\|createObjectURL\|revokeObjectURL` frontend/src/ |
| N147 (Python import + 端到端验证) | `ruff check --select F821` undefined name + Playwright E2E 截图流 + agent 日志无 NameError | `ruff check --select F821 backend/ agent/` exit 0 |
| N156 (Playwright 前置读代码) | `scripts/e2e/scenarios/ai_qa_chat.py` 注册到 `run_all.py` + grep 前端 store/api 层确认端点 | `pytest scripts/e2e/scenarios/ai_qa_chat.py` + `Glob scripts/e2e/scenarios/*.py` |
| N196 (实机测试四步流程) | 测前截图+OCR 落盘 + 窗口可见性检查 + 日志分段查询 | agent 日志含 单节点执行 + foreground/input_method 检查 |

### ⑱ N118 M2.A 测试套件环境依赖 Y/N 矩阵 (R28 闭环 — N118 强化加项)

> **触发条件** (任意一条即触发):
> - AI 写 GAF bash wrapper 测试 (gaf_init.sh / gaf-commit.sh) 在 Windows 上
> - AI 模拟 session binding hash 验证 (check_session_active.check_session())
> - AI 复制 test fixtures / temp scripts 到临时目录
> - AI 跑测试时遇到 `ModuleNotFoundError` (缺模块) / `FileNotFoundError: bash` / hash mismatch / spec 漂移

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 检测 bash 路径用 helper (`_find_bash()` 扫 Git Bash / MSYS2 / WSL 常见路径) | | `grep "_find_bash\|BASH_EXE" scripts/tests/test_gaf_commit_wrapper.py` |
| 2 | session binding hash 与 `compute_binding_hash()` 口径一致 (no indent, sort_keys=True, ensure_ascii=False) | | `grep "indent" scripts/tests/test_session_active.py` (应无 indent=2) |
| 3 | 复制 fixtures 必含所有依赖模块 (如 `_encoding_safe.py` 跟 `check_session_active.py` 一起复制) | | `grep "_copy_session_script_files\|_encoding_safe" scripts/tests/test_session_active.py` |
| 4 | spec vs code 漂移: 测试侧假设的字段/行为, 必须在 docs/reference/tech-stack.md 有记录 | | `grep "<test_assumption>" docs/reference/tech-stack.md` |
| 5 | 跑测试用 explicit module list (如 `python -m unittest scripts.tests.test_extract_lessons ...`) 不用 `discover` | | `grep "python -m unittest" scripts/tests/run_all.py` |
| 6 | 43+ tests 全过 + 跑 < 2min | | `python scripts/tests/run_all.py` exit 0 |

**AI 必做 (M2.A 测试套件环境依赖硬规则)**:
- ✅ **bash 路径检测**: Windows 上先扫 `D:\Programming\Programming software\Git\bin\bash.exe` / `C:\Program Files\Git\bin\bash.exe` 等常见路径, 找不到再 fail
- ✅ **binding hash 口径**: 测试侧计算 binding hash 必须**完全一致** (no indent, sort_keys, ensure_ascii=False), 否则 `check_session()` 误报 binding 不匹配
- ✅ **模块复制齐**: 复制 test fixture 时, 必查目标脚本的所有 `import` 依赖, 一并复制
- ✅ **spec/code 双向**: 写测试前先 Read 被测脚本, 假设必须**实测验证**一次, 不靠"应该是"
- ✅ **explicit module list**: 跑多个 test module 用空格分隔, 不靠 `discover` (避免 NoneType 错)
- ✅ **跑全套 < 2min**: 43 tests / 2min 是基线, 超 5min 必查慢测试
- ❌ **NEVER 假设 indent=2 (或任何 indent) 是 binding hash 口径** (必 Read `compute_binding_hash()`)
- ❌ **NEVER 用 `bash` 命令不先检测路径** (Windows 上 `bash` 不在 PATH, `FileNotFoundError`)
- ❌ **NEVER 复制 fixture 漏依赖模块** (导致 `ModuleNotFoundError: No module named '_xxx'`)
- ❌ **NEVER 用 `unittest discover` 跑 multi-module** (PathLike object 错)
- ❌ **NEVER 写测试不跑一次验证假设** (spec vs code 漂移, N106 家族)

**预防规则 (N118 提取)**:
- bash wrapper 测试 → 先 `_find_bash()` 检测, 找不到 `skip` 而不是 `fail`
- session binding 测试 → 先 Read `compute_binding_hash()` 拿到口径, 再 `json.dumps(sort_keys=True, ensure_ascii=False)` (no indent)
- 复制 fixtures → 先 `grep "^from\|^import" <target_script>` 列出依赖, 全部复制
- 写测试前 → 跑 1 次被测脚本, 看实际行为, 写测试时**实测**而不是"应该是"

**同根因家族**: N95 (分级分发) + N100 (Set-Content 损坏) + N101 (状态不诚实) + N105 (hook 透传) + N106 (路径漂移) + N110 (lint 阻塞) + N114 (hook 误用) + N116 (并发缺位) + **N118 (本条 测试套件环境依赖)** —— 同根因 (环境/工具/治理缺位)

### N119 命令卡死让用户手动结束 (参考, 无独立 Y/N 矩阵)

> **注**: N119 (M2.B 闭环) 是 N111 (命令超时主动中止) 的强化版本, 关于 "命令卡死让用户手动结束" 的反模式。
> N119 的完整规则在 `project_rules.md §5.9` (88 行新规则: N119 4 原则 + 档位表 + 正确模式 vs 反模式)。
> N119 与 N111 同根因 (工具调用治理缺位), 反思时按 N111 Y/N 矩阵检查即可, N119 提供更细粒度的档位表。
>
> **N119 4 原则** (摘要):
> - ✅ 命令必须设预期时间 (按 5 段判别)
> - ✅ 超预期必须 CheckCommandStatus 查输出
> - ✅ 0 输出 + 超预期必须 StopCommand 杀
> - ✅ 主动结束 ≠ 失败 = AI 成熟标志
>
> **详细**: `failure-modes.md N119` + `architecture-mistakes.md #47`

### ㉖ N142 复制-粘贴重命名必须更新所有标识符 Y/N 矩阵 (R37-P1 闭环 — 加项)

> **触发条件** (任意一条即触发):
> - AI 复制源文件作为新组件 (如拆 page 为多个 Tab)
> - AI 重命名 component 但保留原文件作为新文件 (copy-paste refactor)
> - AI 改 `export function X()` 但没改 `export default X`
> - 浏览器报 `ReferenceError: <OldName> is not defined at <NewFile>:<line>`
> - ALL routes 崩溃 (不只目标页面) + main.tsx 渲染失败

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 复制后 grep 旧函数名: `grep -n "<OldName>" <NewFile>` 应 0 结果 (除 i18n key) | | `grep -n "TemplateAnnotationPage" LiveAnnotationTab.tsx` |
| 2 | `export default <NewName>` 引用已更新 (不是 `<OldName>`) | | `grep "export default" <NewFile>` |
| 3 | Interface 名 / 类型别名已更新 (如 `XProps` → `YProps`) | | `grep "interface.*Props" <NewFile>` |
| 4 | 改完跑 Playwright 烟测 (登录页能渲染 = main.tsx 加载成功) | | `python scripts/e2e/run_all.py browser_login` |
| 5 | 多 Tab 拆分后跑全 4 页 Playwright (不只目标页, 因 ALL routes 会崩) | | verify_r37_p1_playwright.py 跑通 |
| 6 | tsc 0 errors ≠ 运行时可用 — 必跑浏览器烟测 | | 不能只靠 `tsc --noEmit` |

**AI 必做 (N142 硬规则)**:
- ✅ **复制源文件作新组件时, 更新所有标识符**: 函数声明 + `export default` 引用 + interface 名 + 类型别名 + 注释提及
- ✅ **改完 grep 旧名**: `grep -n "<OldName>" <NewFile>` 应 0 结果 (除 i18n key 字符串)
- ✅ **tsc 0 errors ≠ 运行时可用**: TypeScript 对 `export default <UndefinedIdentifier>` 不报错 (退化为 any), 必跑浏览器烟测
- ✅ **改完跑 Playwright 全页烟测**: ALL routes 会因 module 加载失败崩, 不只目标页
- ❌ NEVER 只改函数声明不改 `export default X` (X 是引用, 不是声明)
- ❌ NEVER 信 `tsc --noEmit` 通过就以为运行时可用 (运行时 ReferenceError tsc 抓不到)
- ❌ NEVER 改完只测目标页面 (main.tsx 加载失败 = ALL routes 崩)

**同根因家族**: N14 (假实现) + N126 (文档虚报) + N135 (批量重构后浏览器验证) + **N142 (本条 复制-粘贴重命名缺位)** —— 同根因 (重命名 + 验证缺位)

### ㉗ N143 认证图片端点必须 axios blob + objectURL Y/N 矩阵 (R37-P1 闭环 — 加项)

> **触发条件** (任意一条即触发):
> - AI 用 `<img src={url}>` 或 `new Image().src=url` 加载 `@permission_classes([IsAuthenticated])` 图片端点
> - 浏览器 console 报 `401 Unauthorized` 加载图片失败
> - AI 用 `client.get(absolute_url)` 但 `client.baseURL` 已含同一前缀 (双重前缀 404)
> - 浏览器原生 `<img>` 标签加载 JWT 端点

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | IsAuthenticated 图片端点不用 `<img src=url>` (浏览器不带 JWT) | | grep `<img.*src=` 看是否含 auth 端点 URL |
| 2 | 改用 `client.get(stripped_url, { responseType: 'blob' })` + `URL.createObjectURL()` | | grep `responseType.*blob\|createObjectURL` |
| 3 | axios baseURL 双重前缀已 strip (`url.replace(/^\/api\/v2/, '')`) | | grep `replace.*api.*v2` |
| 4 | cleanup 时 `URL.revokeObjectURL()` 防内存泄漏 | | grep `revokeObjectURL` |
| 5 | Playwright 监听 `page.on('response')` 抓 401/404 (tsc 抓不到) | | verify script failed responses = [] |
| 6 | 改完跑 Playwright 全页烟测 + 监听 network 失败响应 | | verify_r37_p1_playwright.py failed responses = [] |

**AI 必做 (N143 硬规则)**:
- ✅ **IsAuthenticated 图片端点用 axios blob + objectURL**: 浏览器原生 `<img>` 不带 `Authorization: Bearer` header, 必用 axios 拿 blob 再 `createObjectURL`
- ✅ **strip axios baseURL 前缀**: `client.baseURL='/api/v2'` + `image_url='/api/v2/...'` (绝对路径) → 必 `image_url.replace(/^\/api\/v2/, '')` 否则双重前缀 404
- ✅ **cleanup `revokeObjectURL`**: useEffect return cleanup 时 `URL.revokeObjectURL(createdUrl)` 防内存泄漏
- ✅ **Playwright 监听 failed responses**: `page.on('response', ...)` 抓 401/404, tsc 抓不到 network 失败
- ❌ NEVER 用 `<img src={auth_url}>` 加载 IsAuthenticated 端点 (浏览器不带 JWT, 401)
- ❌ NEVER `client.get(absolute_url)` 不 strip baseURL 前缀 (双重前缀 404)
- ❌ NEVER 创建 objectURL 不 cleanup (内存泄漏)
- ❌ NEVER 信 tsc 通过就以为图片加载成功 (network 失败 tsc 抓不到)

**同根因家族**: N118 (测试环境假设) + N131 (浏览器自动化) + N135 (批量重构后浏览器验证) + **N143 (本条 认证图片加载缺位)** —— 同根因 (浏览器 + 认证 + 验证缺位)

### ㉘ N147 Python 新库/typing 使用必须同步 import + commit 前端到端验证 Y/N 矩阵 (P-004 R37-P2 闭环 — 加项)

> **触发条件** (任意一条即触发):
> - AI 在 Python 文件中添加新库调用 (如 `ThreadPoolExecutor(...)`, `Path(...)`, `cv2.imread(...)`)
> - AI 添加新 typing 类型注解 (如 `Optional[List[...]]`, `Tuple[...]`, `Set[...]`)
> - AI commit 后 agent 日志报 `NameError: name 'X' is not defined`
> - AI 只跑了 `python -c "import module"` 就以为功能可用
> - 涉及线程/异步/截图流等运行时才触发的功能

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 新增库调用 (如 `ThreadPoolExecutor`) → 顶部 import 已添加？ | | `grep "^from concurrent" <file>` 或 `grep "^import" <file>` |
| 2 | 新增 typing 类型 (如 `List`/`Tuple`/`Set`/`Union`) → typing import 覆盖？ | | `grep "^from typing import" <file>` 含所有用到的类型 |
| 3 | 新增类型注解 (`Optional[...]`/`Dict[...]`) → 内部类型已导入？ | | `grep -n ": .*List\|: .*Tuple" <file>` 找用法再核对 import |
| 4 | 涉及线程/异步/截图 → 端到端验证触发过功能？ | | Playwright E2E 或手动浏览器操作触发 |
| 5 | `python -c "import module"` 通过 ≠ 功能可用 → 跑过实际调用？ | | agent 启动 + 触发截图流，看日志无 NameError |
| 6 | commit 前跑 `ruff check F821` (undefined name)？ | | `ruff check --select F821 <file>` exit 0 |

**AI 必做 (N147 硬规则)**:
- ✅ **添加新库使用 → 立即检查顶部 import**: `ThreadPoolExecutor(...)` → `from concurrent.futures import ...`？`Optional[List[...]]` → typing 有 `List`？`Path(...)` → `from pathlib import Path`？
- ✅ **commit 前端到端验证 (不只是启动服务)**: 启动 agent ≠ 截图流工作 (截图流要前端触发才启动)；必须触发功能 (Playwright E2E 或手动浏览器操作)
- ✅ **Python 项目 commit 前 ruff/pyflakes 检查**: `ruff check F821` 能发现未定义名称 (undefined name)
- ✅ **静态检查通过 ≠ 运行时可用**: `python -c "import module"` 只验证顶部 import 解析，不验证函数体内 NameError
- ❌ NEVER 只跑 `python -c "import module"` 就以为功能可用 (函数体内 NameError 要运行时才暴露)
- ❌ NEVER 信 lint 通过就以为运行时可用 (lint 不一定覆盖 F821 undefined name)
- ❌ NEVER commit 涉及线程/截图/异步的功能而不触发实际功能验证

**预防规则 (N147 提取)**:
- 添加新库调用 → 立即 grep 顶部 import 确认已添加
- 添加新 typing 类型 → 立即 grep `from typing import` 确认覆盖
- 涉及运行时才触发的功能 (线程/异步/截图流) → commit 前必跑端到端验证 (启动服务 + 触发功能 + 看日志无异常)
- Python 项目 → commit 前跑 `ruff check --select F821` 抓 undefined name

**反模式代码示例**:
```python
# ❌ BAD: 用了 ThreadPoolExecutor 但没 import
import threading
from typing import Any, Callable, Dict, Optional  # 缺 List

class Handler:
    def __init__(self):
        self._filter: Optional[List[str]] = None  # NameError: List (运行时求值注解)
    
    def run(self):
        with ThreadPoolExecutor(max_workers=4) as pool:  # NameError: ThreadPoolExecutor
            pass

# ✅ GOOD: 同步添加 import
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed  # 新增
from typing import Any, Callable, Dict, List, Optional  # 加 List

class Handler:
    def __init__(self):
        self._filter: Optional[List[str]] = None  # OK
    
    def run(self):
        with ThreadPoolExecutor(max_workers=4) as pool:  # OK
            pass
```

**实测基线 (N147 闭环)**:
- 引入 bug commit `-` (P-004 R37-P2) — agent 截图流线程 NameError × 10 后停止
- 修复 commit `-` — Playwright E2E 收到 2 frames, brightness=77.28, 0 errors

**同根因家族**: N135 (前端批量重构后浏览器验证) + N128 (文档状态 3 步验证) + N129 (审计 3 棵代码树) + **N147 (本条 Python import 遗漏 + commit 前端到端验证)** —— 同根因 (静态检查通过 ≠ 运行时可用 + 验证缺位)

### ㉙ N156 写 Playwright E2E 测试前必先读前端代码确认实际端点 Y/N 矩阵 (闭环)

> **触发条件** (任意一条即触发):
> - AI 要写 Playwright/browser-use E2E 测试某个 UI 功能
> - AI 已用 PowerShell/Invoke-WebRequest 测试过后端 API 端点并通过
> - AI 假设前端 UI 调用的端点和 API 测试的端点相同
> - Playwright 测试失败但 AI 没有先读前端代码就修改测试
> - 临时测试脚本验证通过后没有持久化到 `scripts/e2e/scenarios/`

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 写 Playwright 测试前，Grep 了前端 store/api 层确认实际调用的端点？ | | `Grep "fetch.*api\|client\.\(get\|post\)" frontend/src/stores/ frontend/src/api/` |
| 2 | API 测试通过后，确认 UI 调用的是同一个端点？ | | `Grep "<endpoint>" frontend/src/` 确认前端调用路径 |
| 3 | 测试失败后，先读前端代码再修改测试（不盲目重试）？ | | Read 前端组件 + store 确认实际调用链 |
| 4 | 临时测试脚本验证通过后，持久化到 `scripts/e2e/scenarios/`？ | | `Glob scripts/e2e/scenarios/*.py` 含新脚本 |
| 5 | 发现预存 bug 时，在当次任务内修复或登记 tech-debt？ | | 不留给后续，不悬空 |

**AI 必做 (N156 硬规则)**:
- ✅ **写 Playwright E2E 测试前，必 Grep 前端代码**: 确认 `fetch()`/`client.get()`/`client.post()` 实际调用的后端端点
- ✅ **"API 通过" ≠ "UI 通过"**: 前端可能调用完全不同的端点（如 Pipeline vs Chat）或调用不存在的端点（404）
- ✅ **测试失败先读代码**: 不要盲目修改测试选择器或重试，先 Read 前端组件 + store 找根因
- ✅ **临时测试持久化**: `.trash/` 中的临时测试验证通过后，持久化到 `scripts/e2e/scenarios/` 作为回归覆盖
- ❌ NEVER 假设 UI 调用的端点和你 API 测试的端点相同
- ❌ NEVER 测试失败后盲目重试（改选择器、加 timeout）而不读前端代码
- ❌ NEVER 临时测试用完即丢（`.trash/` 删除后无回归覆盖）

**预防规则 (N156 提取)**:
- 写 Playwright 测试前 → Grep `frontend/src/stores/` + `frontend/src/api/` 确认 `fetch()`/`client.get()` 调用的端点
- API 测试通过后 → Grep 前端代码确认 UI 调用同一端点
- 测试失败 → 先 Read 前端组件 + store，再修改测试
- 临时测试通过 → 持久化到 `scripts/e2e/scenarios/` + 注册到 `run_all.py`

**反模式示例**:
```
❌ BAD (AI 实际执行):
  1. PowerShell 测 /ai/chat/ API → ✅
  2. 假设 UI 也用 /ai/chat/ → 写 Playwright 测 /ai/assistant
  3. 测试失败 → 盲目改选择器重试 → 又失败
  4. 才读前端代码 → 发现 UI 用 generate-pipeline-stream

✅ GOOD:
  1. PowerShell 测 /ai/chat/ API → ✅
  2. Grep "ai/chat" frontend/src/ → 发现只有 api/ai.ts 用它
  3. Grep "fetch.*ai" frontend/src/stores/ → 发现 AiAssistantPanel 用 generate-pipeline-stream
  4. 先修 bug → 再写测试 → 一次通过
```

**实测基线 (N156 闭环)**:
- 引入问题: 2 轮 Playwright E2E 测试失败 (假设端点错误)
- 修复 commit `-`: model_name NameError + QAPanel 改用 /qa/ask/
- 回归测试: `scripts/e2e/scenarios/ai_qa_chat.py` 注册到 `run_all.py`

**同根因家族**: N129 (审计 3 棵代码树) + N135 (批量重构后浏览器验证) + N147 (静态检查通过 ≠ 运行时可用) + **N156 (本条 先测试后理解)** —— 同根因 (验证不充分 + 先行动后理解)

### ㉚ N196 实机测试 pipeline 四步流程 Y/N 矩阵 (s28 补登 — 2026-08-17)

> **触发条件** (任意一条即触发):
> - AI 要跑真实设备/模拟器上的 pipeline 测试 (用户提供 task json)
> - 节点失败时 AI 准备直接重跑而不确认画面状态
> - 设备发现显示 ADB 在线但点击不生效
> - AI 无法从日志定位失败节点

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 测前确认: 截图 + OCR 推断当前画面处于节点链路哪个阶段? | | 截图落盘 + OCR 输出记录 |
| 2 | 当前画面不在起点时, 问了用户返回路径 (不假设画面)? | | 对话记录含用户返回指引 |
| 3 | 设备发现: 区分 "ADB 在线" vs "窗口可点击" (模拟器最小化仍可跑 ADB)? | | 窗口可见性检查 (前台窗口标题/坐标) |
| 4 | 点击失败时先查窗口前台状态 + input_method (SendInput 需前台 / PostMessage 对 Unity 无效)? | | 日志含 input_method + foreground 检查 |
| 5 | 分阶段执行: pipeline 分节点跑, 每节点验证后再进下一节点 (非全量盲跑)? | | 单节点执行日志 |
| 6 | 日志驱动诊断: 失败时读 agent 日志定位卡在第几个节点, 而非反复重试? | | 日志分段查询 |

**AI 必做 (N196 硬规则)**:
- ✅ **测前必做 3 件事**: 设备发现 (目标设备在线) + 截图 OCR (当前画面) + 对照节点链路 (第一个节点期望什么画面)
- ✅ **画面不匹配 → 问用户**: "当前在 X 页面, 第一个节点需要 Y 页面, 怎么返回?" (不假设画面)
- ✅ **ADB 在线 ≠ 窗口可点击**: 模拟器最小化也能跑 ADB, 必须额外检查窗口可见性
- ✅ **点击失败优先查前台状态 + input_method**: SendInput 需要前台, PostMessage 对 Unity 游戏无效
- ❌ **NEVER 不确认画面状态直接重跑 pipeline** (首个节点必失败)
- ❌ **NEVER 测试中断后假设画面回到起点** (下次测试前重新确认)
- ❌ **NEVER 点击不生效时只调坐标不查窗口前台状态**

**预防规则 (N196 提取)**:
- 跑 pipeline 前 → 截图 + OCR + 对照节点链路
- 设备发现 → 分两层: ADB 在线 + 窗口可见
- 点击失败 → 查 window_foreground + input_method + 日志
- 测试中断 → 下次测试前问用户怎么返回起点

**实测基线 (N196 闭环)**:
- 触发: 用户测试 `resources/BrownDust-II/tasks/get_email.json`, 4 个连续问题 (无测前确认 / 中断后不问返回路径 / ADB 在线误判窗口在线 / 点击没生效不查前台)
- lesson: `lessons/N196-real-device-pipeline-test-workflow.md` (2026-07-30, priority: high)
- 关联: N195 (透明 PNG alpha mask, 同批测试暴露) + N191 (schema 数据流) + N182/N184 (三维根因 + 节点观测性)

**同根因家族**: N133 (模拟器设备控制 gap) + N156 (测试先于理解) + **N196 (本条 实机测试流程)** —— 同根因 (设备/测试认知不完整 + 验证缺位)

### ㉛ N209 改码后服务未重启 → E2E 假绿 Y/N 矩阵 (2026-08-28 补登)

> **触发条件** (任意一条即触发):
> - 改 backend/agent 代码后, E2E 结果全 SUCCESS 但新参数/新分支未生效
> - 修改了 serializers/API 签名/节点参数, 担心旧进程仍加载旧代码
> - E2E 部分入口过、部分入口失败, 且旧签名"恰兼容"掩盖了新代码未加载

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 改码后确认服务已加载新代码 (daphne/celery/agent 进程启动时间或重启验证)? | | 进程 start time / 重启后重跑 |
| 2 | 新参数/新分支有独立 E2E 用例 (防"旧签名恰兼容"掩盖)? | | 新增用例覆盖新分支 |
| 3 | E2E 不全会先查服务是否加载新代码 (与 N99 Vite 缓存同族)? | | 进程时间 + 日志版本号 |

**AI 必做 (N209 硬规则)**:
- ✅ 改 backend/agent 代码后, E2E 前必重启相关服务或确认进程已加载新代码
- ✅ 新参数/新分支加独立 E2E 用例, 不依赖旧用例"恰兼容"
- ❌ **NEVER 把 E2E 不全部通过直接当代码 bug 排查, 先确认服务加载的是新代码**

**实测基线 (N209 闭环)**:
- 触发: 2026-08-28 TaskChain B1 force_agent_id 500, Task/Pipeline 旧签名恰兼容显示 SUCCESS
- lesson: `lessons/testing_2026-08-28_n209-restart-backend-before-e2e.md`

**同根因家族**: N99 (Vite 缓存旧代码) + **N209 (本条 服务未重启假绿)** —— 同根因 (改了代码但执行环境仍加载旧代码)

### ㉜ N210 E2E 前置配置缺失就跳过 Y/N 矩阵 (2026-08-28 补登)

> **触发条件** (任意一条即触发):
> - E2E 前置缺失 (缺 GameProfile.routine / 设备绑定 / 默认链) 准备标跳过
> - 用户反馈某入口"跑不通"而 AI 想以"环境前置缺失"跳过

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 前置缺失时主动构造配置把入口跑通 (而非跳过)? | | 构造后 E2E 通过 |
| 2 | 构造成本超出测试价值时显式告知用户 (而非默认跳过)? | | 对话含成本评估说明 |

**AI 必做 (N210 硬规则)**:
- ✅ E2E 前置缺失 ≠ 跳过 — 应主动构造配置 (建 routine / 绑设备 / 建默认链) 把入口跑通
- ✅ 仅当构造成本超出测试价值并显式告知时, 才允许标记跳过
- ❌ **NEVER 以"环境前置缺失"默认标跳过**

**实测基线 (N210 闭环)**:
- 触发: 2026-08-28 用户两次纠正 (缺 GameProfile.routine / 设备绑定 / 默认链)
- lesson: `lessons/testing_2026-08-28_n210-e2e-prereqs-should-be-built.md`

**同根因家族**: N196 (实机测试四步流程) + **N210 (本条 E2E 前置构造)** —— 同根因 (E2E 前置准备不完整)

---

