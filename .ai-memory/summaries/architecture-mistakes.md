---
date: 2026-01-01
maintainer: manual
symptom: [architecture, design, mistake, history]
solution: 架构与设计错误清单 — 历史 R1-R30+ 反模式与正确做法
diff_keywords: ["failure", "modes", "failure-modes", "code", "rules", "code-rules", "library", "conflicts", "library-conflicts", "project", "project_rules", "skill"]
related_files:
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/summaries/code-rules.md
  - .ai-memory/summaries/library-conflicts.md
  - .skills/rules/project_rules.md
  - .skills/skills/gaf-reflect-and-evolve/SKILL.md
created_by: AI
priority: high
last_manual_edit: 2026-07-15
load_when: [on-demand]
source: handwritten
---


> **v9.5 N## 冗余清理 (2026-07-20, spec-51)**: 删除 36 个 N## 编号段落 (2013 行冗余拷贝), N## 教训单一权威源在 `.ai-memory/lessons/`。本文件仅保留早期未编号教训 (1-27) + v8.4 反思 (#28/#34/#49) + Vite (47)。


# Architecture & Design Mistakes

> **HISTORICAL_REFERENCE: 早期架构教训历史参考 (L3 按需加载).**

> 本文件为早期架构教训历史参考(教训 1-27),当前反模式索引以 `failure-modes.md` N## 体系为单一权威源。

> These are ACTUAL architectural errors encountered in GAF development.

> Last updated: 2026-07-18 (TD-175 Spec 3 review: 内容审查无需大改, 上次重大变更仍为 2026-07-15 TD-120 撤销拆分)

> **v9.2 撤销拆分 (2026-07-15, TD-120)**: 2026-07-09 (commit -) 将本文件拆分为 `architecture/` 子目录下 11 个 sub-file (历史数字, 当前动态计数), 但拆分脚本在 Windows 上编码处理不当, 导致所有 sub-file 中文内容乱码 (UTF-8 字节被误解码为 cp936/gbk)。由于子文件从未正确显示过, 且本完整文件是正确编码的 UTF-8, 按 §2.0.5 ②归一化原则撤销拆分, 恢复为单一权威源。原 `architecture/` 子目录已删除。

> **历史**: 2026-07-09 拆分前为本文件 (150KB), 拆分后本文件改为 9.4KB 索引 + 11 sub-file (历史数字, 当前动态计数)。2026-07-15 撤销拆分, 恢复原始 150KB 内容。

> **v9.4 §0 删除 (2026-07-19, spec-38 Phase 7)**: 原 §0 (N151) / §0.1 (N167) / §0.2 (N169) 三段 N## 索引已删除, N## 索引单一权威源在 `.ai-memory/meta/failure-modes.md` (避免双源维护漂移)。本文件仅保留 §1+ 历史架构教训详情。

---



## 1. Agent Authentication Chicken-and-Egg Problem



- **Problem**: First connection has no Agent record → WebSocket rejects connection → Agent never registers

- **Root cause**: `_authenticate_agent(None)` returns None for local Agent without prior record

- **Fix**: Use `get_or_create` + `update_or_create` for first-time registration

- **Rule**: Never assume Agent record exists before first connection. Always auto-create with `is_local=True`



---



## 2. State Synchronization Between REST API and WebSocket



- **Problem**: Dashboard AgentHealthPanel REST API shows "no Agents" but WebSocket sees 16 agents

- **Root cause**: REST API and WebSocket maintain separate state sources

- **Status**: Logged for Phase 2+ integration

- **Rule**: When designing status display, ensure single source of truth. Do not mix REST and WebSocket state.



---



## 3. PipelineEngine Context Missing Device



- **Problem**: `PipelineEngine.load()` did not set `context.device`

- **Impact**: Pipeline nodes cannot access device instance

- **Fix**: Add device parameter to context initialization

- **Rule**: Always ensure execution context has all required dependencies (device, agent, resource_pack)



---



## 4. Fragile Internal Attribute Coupling



- **Problem**: `health_checker` extracts hwnd via `device._window_mgr._hwnd` — fragile internal coupling

- **Impact**: Any change to WindowsDevice internal structure breaks health_checker

- **Status**: Logged for refactoring

- **Rule**: Never access private attributes (`_xxx`) of other components. Use public interface methods.



---



## 5. WebSocket Event Not Listened on Frontend



- **Problem**: Frontend does not listen to `device.status_changed` WebSocket events

- **Impact**: Device status does not update in real-time on UI

- **Rule**: Every WebSocket broadcast must have a corresponding frontend listener



---



## 6. Missing Auto Health Check Scheduler



- **Problem**: No periodic automatic health check — requires manual API trigger

- **Status**: Logged for Agent background thread implementation

- **Rule**: Critical monitoring must be automatic, not manual



---



## 7. Duplicate Input Module Code



- **Problem**: `backend input module (已重构到 worker/src/input/)` and `agent input controller (已重构)` exist simultaneously — same functionality, two implementations

- **Impact**: Violates DRY principle, maintenance burden

- **Status**: Logged for R9-A unification

- **Rule**: One responsibility = one module. Never duplicate core logic across backend and agent.



---



## 8. Mock Implementations in Production Code



| Module | Mock Behavior | Real Implementation Needed |

|--------|--------------|---------------------------|

| `template_match.py` | Returns hardcoded coords (100,200) | cv2.matchTemplate |

| `click.py` | Logs coordinates, no real click | Real Device.click() |

| `device_control.py` | Mock state machine | Real device control |

| `OCR node` | Mock skeleton, no registry | Real batch_ocr integration |



- **Rule**: Never commit mock implementations as "done". Mark as 🔧 and track in pending-items.



---



## 9. Screenshot Resolution Not Saved on Registration



- **Problem**: Screenshot API returns `{width:0, height:0}` because resolution not saved during registration

- **Impact**: Subsequent screenshots have unknown dimensions

- **Rule**: Save all required metadata (resolution, capabilities) during device registration



---



## 10. ADB Serial Number Inconsistency



- **Problem**: Scanner finds `127.0.0.1:5555` but ADB reports `emulator-5554`

- **Root cause**: LDPlayer uses network ADB with different serial format

- **Status**: Known LDPlayer characteristic, not a bug

- **Rule**: Handle emulator-specific serial formats. Do not assume uniform naming.



---



## 11. Task Model Unique Constraint After M2M→FK Change



- **Problem**: `unique_together` constraint on Task model breaks after M2M→FK migration

- **Fix**: Implement uniqueness through serializer instead of DB constraint

- **Rule**: When changing relationship types (M2M→FK), verify all constraints still valid



---



## 12. API URL Mismatch Between Frontend and Backend



| Frontend URL | Backend URL | Files Affected |

|-------------|------------|---------------|

| `/api/v2/scheduled-tasks/` | `/api/v2/tasks/scheduled-tasks/` | 5 places |

| `/users` | `/accounts/users/` | settings.ts |

| `/marketplace/items/` | `/marketplace/` | MarketplacePage |



- **Rule**: Always verify API endpoints match backend URL routing. Frontend types must match backend response schema.



---



## 13. Screenshot Benchmark Not Auto-Integrated



- **Problem**: Benchmark exists but not called on device connection

- **Impact**: Device does not automatically select optimal screenshot method

- **Status**: Logged for R9-D

- **Rule**: Performance benchmarks should run automatically on connection, not manually



---



## 14. Dead Code Accumulation



- **Problem**: `ConfirmDialog.tsx` existed as dead code, only discovered during cleanup
- **Case (2026-08-28)**: `execution_planner.py` left in place because unit tests still imported it — but it had zero production callers after TaskExecuteView was deleted. "Has test callers" ≠ "has production value"; tests only prove the function exists, not that anything uses it.

- **Rule**: Dead code detection must be a standard step in every refactoring
- **Judge**: after removing the only production caller, grep the module's symbols across `backend/` non-test code; if no non-test references remain, delete the module AND its dedicated tests in the same change (test-only survival is not a keep reason).



---



## 15. Document Search Name ≠ Actual Class Name



- **Problem**: Searching "连接池" (connection pool) found nothing because actual class is `FramePool`

- **Rule**: Use multiple search patterns. Class names may differ from documentation terms.



---



## 16. Pending Roadmap Status Markers Not Honest (Phase R6)



- **Problem**: `pending-roadmap.md` listed R6-A1~B2 as ❌ (not implemented), but code already existed and was fully functional. Wasted time re-implementing what was already done.

- **Root cause**: Previous Phases marked features as ❌ in roadmap even after implementation, without updating the document.

- **Impact**: AI spent time "verifying" instead of directly validating, confused about what needed work.

- **Fix**: Use honest status markers: ✅ = verified (browser tested), 🔧 = code exists (not verified), ❌ = not implemented

- **Rule**: After every Phase, update status markers in `pending-roadmap.md` immediately. Never mark ❌ for implemented code.



---



## 17. Verification Script File Encoding Issues in PowerShell (Phase R6)



- **Problem**: `Set-Content -Path` corrupts Python f-strings and special characters, causing `SyntaxError: unterminated f-string literal` and `SyntaxError: invalid syntax`. Wasted 3+ iterations fixing encoding instead of doing real verification.

- **Root cause**: PowerShell 5 `Set-Content` does not properly handle Python string formatting syntax.

- **Fix**: Use `Write` tool to create `.py` files directly, or write verification logic inline with proper escaping.

- **Rule**: Do NOT use `Set-Content` for Python scripts. Use `Write` tool for file creation. For quick checks, prefer `Grep` + `Read` over custom scripts.



---



## 18. Agent Auto-Connects on Backend Start (Phase R6 Discovery)



- **Discovery**: When backend starts, Agent process automatically connects via WebSocket without manual start. This is due to a background Agent process running from a previous session.

- **Impact**: Can be misleading — appears as "Agent auto-connects" but is actually a stale process.

- **Rule**: Before testing Agent connectivity, check for existing Agent processes. Use `tasklist | findstr python` to find stale agents.



---



## 19. No Pipeline Execution API Endpoint (Phase R6 Gap)



- **Problem**: No REST API endpoint exists to trigger Pipeline execution. Can only verify code path exists, cannot actually run a Pipeline end-to-end.

- **Impact**: R6-C2 "端到端流程验证" can only verify code correctness, not actual execution.

- **Status**: [B] class — requires Pipeline API implementation (future Phase)

- **Rule**: Infrastructure code must have API entry points for testing. Code without API = untestable.

---

## 20. File Corruption via Escape Characters (Phase R20 Discovery)



- **Problem**: `backend/workers/views.py` was corrupted with escape sequences (`_` → `\_`, Chinese → mojibake), causing Django SyntaxError on startup.

- **Root cause**: Unknown — likely from a bulk edit operation that introduced character escaping. The file had 32+ `\_` sequences and garbled Chinese comments.

- **Impact**: Backend completely unable to start. The corruption was committed to git in Phase R19.

- **Fix**: Restored from last known good version (commit -), then re-applied R19 error handling changes using proper tools.

- **Rule**: After any bulk file edit, ALWAYS verify syntax with `py_compile.compile(file, doraise=True)`. Spot-check for `\` before `_` patterns.



---



## 21. Agent/Device Status Logic Error: `=== 'online'` Misses `idle` State (Phase R20 Discovery)



- **Problem**: Dashboard "在线 Agent" count always showed 0 despite Agent being online and healthy.

- **Root cause**: Frontend used `status === 'online'` to filter, but backend returns 3 states: `online` (working), `idle` (online but idle), `offline`. Most Agents are in `idle` state when not running tasks.

- **Fix**: Changed all 10 occurrences across 9 files from `=== 'online'` to `!== 'offline'`.

- **Rule**: When filtering for "online" entities, use negative logic (`!== 'offline'`) to include all non-offline states. This is more robust against new status values being added.



---



## 22. Import Path Depth Error in Page-Level Components (Phase R20 Discovery)



- **Problem**: `ConfigManagementPage.tsx` import path `../../utils/errorHandler` caused Vite resolution failure ("Failed to resolve import").

- **Root cause**: `ConfigManagementPage.tsx` lives in `src/pages/` (depth 1 from src), so correct path is `../utils/` not `../../utils/`. Other page components in deeper directories (e.g., `src/pages/Resources/`, `src/pages/Dashboard/`) correctly used `../../utils/`.

- **Fix**: Corrected to `import { classifyError } from '../utils/errorHandler'`.

- **Rule**: When adding imports, verify directory depth. Files directly under `src/pages/` need `../utils/`, files in subdirectories need `../../utils/`.



---



## 23. Partial Error Handling Rollout Causes Silent Failures (Phase R20 Lesson)



- **Problem**: Phase R20 only applied `classifyError()` to Login page (6 catch blocks). User reported "资源包界面点击就报错，找不到" — the error message was a generic fixed string with no detail.

- **Root cause**: Error handling fix was scoped too narrowly. 11 other pages/components still had old-style `catch { message.error('固定') }` patterns.

- **Fix**: Full frontend audit found 28 additional catch blocks across 11 files, all updated to `classifyError()`.

- **Rule**: When establishing a new pattern (like unified error handling), apply it GLOBALLY across the codebase, not just to the initially reported location. Use grep to find ALL instances of the old pattern.



---



## 24. AI Passive Execution: Forcing User to Manually Run Commands (M0 Closure Discovery, 2026-06-15)



- **Problem**: During M0 closure verification, AI told user "请手动跑 `pip install pre-commit`" and "请手动执行 `bash GAF/scripts/gaf_init.sh`". User feedback: *"这次实现很多时候都需要我主动点击运行，这不太好"*.

- **Root cause** (5 layers):

  1. **Capability bias**: AI tends to "output instructions" instead of "execute directly" — easy to write code, lazy to run commands

  2. **Completion illusion**: AI confuses "telling user what to do" with "doing the task"

  3. **Missing constraint**: spec/plan lacked hard rule against "delegating execution to user"

  4. **Tool-use mismatch**: AI has `RunCommand` but uses it inconsistently; treats "guidance" as delivery

  5. **Session split**: Code-writing session vs. execution session mental model disconnected

- **Impact**:

  - User experience degraded (3+ manual clicks per task)

  - Spec "closed-loop" claim violated (manual operation = open loop)

  - User trust damaged (AI appears "incomplete")

- **Fix** (3 components):

  1. **Spec hard constraint** (spec.md §"AI 硬约束" 条款 7):

     > "AI 必须自跑所有验证命令，禁止把命令甩给用户"

  2. **gaf_init.sh self-contained**: auto-detect + auto-install `pre-commit`, auto-run `pre-commit install`

  3. **Pre-commit hook + reflection**: `gaf-auto-run-check` hook scans AI output for "请手动跑" / "请刷新" / "请重启" / "可以测试了" patterns → reject commit + force AI to self-execute

- **Rule**:

  - ✅ Write code → immediately `RunCommand` to verify (don't output "请跑")

  - ✅ Verification fails → immediately `RunCommand` to fix (don't output "请修")

  - ✅ New tool needed → immediately `RunCommand pip install` (don't output "请安装")

  - ❌ NEVER output "请手动跑" / "请刷新" / "请重启" / "可以测试了"

  - ❌ NEVER assume "user will help me run" — user is reviewer, not executor

- **Reflection question** (added to gaf-dev-workflow §3.2):

  > "本轮所有验证命令，AI 是不是都自己跑过？列出 X/Y 比例。"

- **Related**: failure-modes N93, code-rules §5.2 (Shell 命令限制) — same root cause different surface



---



## 25. PowerShell CJK Garble Silent Regression (M0 Closure, 2026-06-15)



- **Problem**: 5 verification scripts (`check_3step_evidence.py`, `check_lessons_updated.py`, `check_spec_consistency.py`, `sync_decision_tree.py`, `sync_ai_memory.py`) all output mojibake like `✅→鉁?` `含 5 个→鍚?5 涓?` in PowerShell 5 console.

- **Root cause** (3 layers — 必须全修才能 100% 解决):

  1. **Layer 1 (Python 端)**: `sys.stdout.encoding` 在 PowerShell 5 下默认 cp936/cp437 → UTF-8 字符编码失败

  2. **Layer 2 (Bash 端)**: bash wrapper 没设置 `PYTHONIOENCODING` → 子 Python 进程继承默认编码

  3. **Layer 3 (PowerShell 5 端 — 最隐蔽)**: 即便 Python 输出是 UTF-8 字节,PowerShell 5 接收 native command stdout 时**会按系统编码 cp936 解码** → 输出管道就 mojibake

- **Impact**: AI 看不到自己的验证输出,debug 困难,看起来不专业

- **Fix** (3 层全覆盖):

  1. **Layer 1**: 创建 `scripts/_encoding_safe.py` + 所有 CLI 脚本首行 `import _encoding_safe`

  2. **Layer 2**: `gaf_init.sh` 头部 `export PYTHONIOENCODING=utf-8` + `export LC_ALL=C.UTF-8`

  3. **Layer 3 (🆕 2026-06-15 验证)**: AI 在 PowerShell 5 下跑命令时必须用 `> file` 重定向 + `Get-Content -Encoding UTF8` 读取,绕过 PowerShell 5 stdout 解码 bug

     ```powershell

     # ✅ 正确（PowerShell 5 下 UTF-8 输出捕获）

     python script.py > "$env:TEMP\out.txt" 2>&1

     Get-Content -Raw -Encoding UTF8 "$env:TEMP\out.txt"

     

     # ❌ 错误（会乱码,即使 Python 端修复了）

     python script.py | Select-Object -First 5

     ```

- **Rule**:

  - ✅ 任何新 CLI 脚本 → 首行 `import _encoding_safe`

  - ✅ 任何新 bash wrapper → 头部 `export PYTHONIOENCODING=utf-8`

  - ✅ PowerShell 5 下 AI 跑命令 → 重定向到文件再 UTF-8 读取

  - ❌ NEVER 依赖 PowerShell 5 stdout 管道显示 UTF-8 内容

- **Related**: failure-modes N92, #20 (file corruption — same encoding family), `gaf-dev-workflow` §2.3 (browser-use 已用 `$env:PYTHONIOENCODING='utf-8'`)

- **Reflection**: N92 是预防性写的,但实际回归在 M0 闭环验证时发生。教训:**预防措施 (N92) 必须配
"执行 hook + 多层验证"** 才有效 — 单层修复不够。



---



## 26. SKILL.md Decision Tree Copies Placed in Wrong Root (M0 闭环, 2026-06-15)



- **Problem**: AI 把 4 份决策树 SKILL.md 副本放在 `.trae/skills/{name}/SKILL.md`（GAF 仓库内）。用户反馈："目前 gaf 是在一个大项目文件夹中,你放在小的他好像识别不到"。

- **Root cause** (4 layers):

  1. **IDE 加载机制误解**: Trae IDE 只扫描 workspace 根的 `.trae/skills/`,不递归扫描子目录

  2. **"仓库内" vs "workspace 内" 概念混淆**: AI 把"GAF 仓库"当 IDE 根,但 IDE 根是 workspace 根(workspace 根 = 父目录)

  3. **缺自动分发机制**: `sync_decision_tree.py` 之前只同步仓库内,没分发到 workspace 根

  4. **AI 自检缺位**: AI 写完 SKILL.md 后没问自己"IDE 能看到吗？"

- **Impact**:

  - 4 份决策树 SKILL.md 在 IDE 中不可见

  - M0 投入
的部分价值丢失(决策树没法触发)

  - 用户必须手动复制 5 个文件(违反 N93 "用户 0 操作")

- **Fix** (3 components):

  1. **sync_decision_tree.py v8.4 双根同步** (N94 修复):

     - 默认行为:同时同步仓库内 4 份 + workspace 根 4 份

     - `detect_workspace_root()` 自动检测(gaf-dev-workflow 标记文件)

     - `--workspace-root <path>` 显式指定

     - `--workspace-root none` 禁用

  2. **gaf_init.sh 验证清单加项**:

     - `workspace 根副本：4/4  仓库内副本：4/4 (两侧都齐)`

  3. **failure-modes N94 + 反思必查项**:

     - 反思环节必查:"AI 写的文件,Trae IDE 看得见吗？"

- **Rule**:

  - ✅ 写 SKILL.md → 立即 sync 到 workspace 根(不要让用户手动复制)

  - ✅ 任何"分发式"AI 文件 → 都要检查 IDE 看得见

  - ❌ NEVER 假设"放在仓库内 IDE 就看得到"

  - ❌ NEVER 让用户手动复制文件

- **Reflection**:

  - 同一个反模式两次( N93 + N94 )都出在"分发"环节 — AI 不擅长"我要分发到哪"的判断

  - 教训:**分发操作必须自动化 + 自动验证** — 不能留给 AI 判断

- **Related**: failure-modes N93, N94, code-rules §5.5 (Single source of truth 分发)



---



## 27. AI Learning Distribution Gap: 1-2 Layers Only (M0.L 闭环, 2026-06-15)



- **Problem**: AI 学到新教训/新经验后,默认只写 `.ai-memory/lessons/<date>-<symptom>.md` 就当完事。用户反馈:"ai 总结学习部分,会提升到文档,skill 和规则里才对吧"。

- **Root cause** (5 layers):

  1. **AI 不擅长"分发"**: 同一反模式三次 (N93/N94/N95) 都出在"分发"环节 — AI 不知道要分发到哪、分发到几层

  2. **缺少"全栈"意识**: AI 写教训时只想到 .ai-memory/ 一处,没想到 spec / skill / rules 也要同步

  3. **缺分发 checklist**: 写完教训后 AI 没清单提醒"5 个层级都分发了吗?"

  4. **没有强制机制**: pre-commit hook 只验证 commit 合规,不验证"教训分发完整度"

  5. **规则不进仓库**: gaf-dev-workflow / project_rules.md 之前只在 workspace 根,团队成员拉新仓库看不到 → 分发链断了

- **Impact**:

  - AI 教训只在 1-2 个层级生效,飞轮效应失效

  - 团队成员/新 AI 看不到完整教训,反复踩坑

  - 反思清单无法验证"5 层都分发"

- **Fix** (5 layer distribution mechanism — M0.L):

  1. **5 层分发清单** (反思环节必填 Y/N 矩阵):

     ```

     ① .ai-memory/ 教训层         Y/N

     ② .ai-memory/summaries/ 架构教训层  Y/N

     ③ spec.md / tasks.md / checklist.md 计划文档层  Y/N

     ④ SKILL.md 工作流/技能层     Y/N

     ⑤ project_rules.md 用户规则层  Y/N

## #28 🆕 v8.4 M0.M: AI 加载机制缺位（"软指导" 被 AI 跳过）

> **历史记录 (M0.M 闭环时状态, v9.3 已演进)**: 本段描述 M0.M 闭环时 (2026-06-15) 的加载机制设计。v9.0+ 已升级: L1 grep pattern 改为 `^\| N[0-9]+` (表格格式, 非 `### N##:`); L2 从 3 文件合并为 1 文件 (`ai-operating-handbook.md`); L3 + promote 闭环保持。保留本段作为历史教训记录, 不再更新内容。

- **Date**: 2026-06-15

- **Symptom**: 用户反馈 "ai 啥时候会读取里面的东西？有提升到 skill 或者规则,文档的计划吗"

- **Context**: M0 闭环后, `.ai-memory/` 目录下创建了 6 份 lessons + meta/failure-modes.md + README, 但 AI 实际**没主动 Read** 这些文件 — 因为 SKILL.md 里只是"soft guidance" (提示字符串), 不是硬约束

- **Root cause (4 维)**:

  1. **软指导 = 看不见的约束**: SKILL.md 中"读 docs/reference/tech-stack.md"是建议,不是硬约束,AI 倾向跳过

  2. **L1/L2/L3 没区分**: 之前都叫"加载",AI 不清楚哪一层是"启动必读"、哪一层是"路由必读"、哪一层是"按需"

  3. **缺加载验证**: gaf_init.sh 之前只验证 session,没验证 L1 加载的 failure-modes.md

  4. **无 hook 阻断**: pre-commit 只检查代码/文档一致性,不检查"AI 是否真读了 .ai-memory/"

- **Why it matters**:

  - 6 份 lessons + 1 份 failure-modes + 3 份骨架文件 → 实际加载率 < 10% (AI 写完就忘)

  - `sync_ai_memory.py --query` 返回 0 时,AI 不知道是 lessons 库空,还是 L2 索引未加载

  - promote_lessons.py 提议 7 条但 AI 不会主动跑 (因为 L3 按需加载也是软指导)

- **What to do**:

  1. **L1 启动硬加载** (M0.M 已实现): gaf_init.sh 步骤 4.5 硬 grep `### N##:` entries, < 5 → exit 1

  2. **L2 路由硬加载** (M0.M 已实现): gaf-orchestrator SKILL.md 决策树 step_1 后加 `l2_hard_load` 段, AI 必读 3 个 .ai-memory/ 文件

  3. **L3 按需 + promote 闭环** (M0.M 已实现): `sync_ai_memory.py --query` + `promote_lessons.py --dry-run` 提议

  4. **pre-commit hook 自动化**: `gaf-promote-lessons` (M0.M 已实现), commit 前自动跑

  5. **gaf-dev-workflow §3.2 反思清单加 ⑦**: "L1/L2/L3 加载是否完整?列出 Y/N 矩阵"

- **Rule**:

  - ✅ 任务开工前 → 必跑 `gaf_init.sh` (L1 硬加载触发)

  - ✅ 决策树 step_1 后 → 必 Read 3 个 L2 文件 (不允许跳过)

  - ✅ 写代码前 → 必跑 `sync_ai_memory.py --query <keyword>` (L3 按需)

  - ✅ 反思环节 → 必填 L1/L2/L3 Y/N 矩阵 (缺一即视为未闭环)

  - ✅ 高频教训 → 跑 `promote_lessons.py --dry-run` 看是否需提升到规则/SKILL/文档层

  - ❌ NEVER 把"看路径名"当"读内容"

  - ❌ NEVER 跳过 L2 软指导 (已升级为 hard-load,违反即反思失分)

- **Reflection**:

  - 用户问"ai 啥时候会读取里面的东西"暴露了飞轮的"读侧"断点 — AI 写很勤,读很懒

  - "soft guidance" → "hard load" 是把 AI 行为从"建议"升级为"约束",质变

  - 同样教训重复 4 次 (N93/N94/N95/N96) 都是"AI 不知道要主动做某事" → 根因都是缺硬约束

- **Related**: failure-modes N96, spec.md §14.7 条款 9, gaf-orchestrator SKILL.md `l2_hard_load` 段, code-rules §5.6 (Hard load > soft guidance)



---



## #34 🆕 v8.4 M1.A.1 闭环: sync_ai_memory.py 写入
 sync-state.json 路径与 spec 漂移 (N106 修复)



- **Date**: 2026-06-16

- **Symptom**: `update_sync_state()` line 468 inline 拼 `state_path = root / "sync-state.json"`,把 `sync-state.json` 写到仓库根;但 spec.md §5 line 224 明确写 `.ai-memory/sync-state.json`。代码与 spec 漂移。`.gitignore` 排除 `sync-state.json` 让漂移在 `git status` 不可见,导致 M1.A.1 验证 11 份顶层时漏看

- **Root Cause** (5 维):

  1. **代码层**: inline 拼路径(`root / "sync-state.json"`)而非用模块级 `SYNC_STATE` 常量

  2. **spec 层**: spec.md §5 写 `.ai-memory/sync-state.json`,与代码漂移

  3. **常量层**: 模块级 `SYNC_STATE = AI_MEMORY / "sync-state.json"` 已正确,但 `update_sync_state()` 没用

  4. **gitignore 层**: `.gitignore` line 133 排除 `sync-state.json`,无论根还是 .ai-memory/ 都不显示变化 → 漂移不可见

  5. **验证层**: sync 工具
·跑通判断只基于 sync 流程,未检查实际写入
位置

- **Fix** (3 步):

  1. 修 `sync_ai_memory.py` line 471: `state_path = root / ".ai-memory" / "sync-state.json"`

  2. 数据迁移: `Move-Item GAF\sync-state.json GAF\.ai-memory\sync-state.json` (保留 30 条 change_history)

  3. 验证: `ls GAF/.ai-memory/sync-state.json` 存在 + `ls GAF/sync-state.json` 不存在 + 重跑 sync 跑通

- **Rule**:

  - ✅ spec 写明路径的文件,代码写入
必须用模块级常量(避免
 inline 漂移)

  - ✅ sync 工具
·跑通 ≠ 路径正确,必须 ls 双重检查

  - ✅ gitignore 的文件不靠 git status 验证,必须 `Test-Path` 验证

  - ✅ spec ↔ code 双向验证 (N95 升级): 5 层分发需双向(spec 写,code 也写)

- **Reflection**:

  - **inline 拼路径 = 漂移温床**: 模块级常量是 single source of truth,函数 inline 拼路径极易与 spec 漂移

  - **gitignore ≠ 不存在**: 文件被 gitignore 不代表它不存在,AI 必须 ls 检查实物

  - **代码-文档漂移 = 隐性 bug**: 路径不一致不会让 sync 失败,但会让 spec 和现实脱节,后续 meta 工具
·读错位置就坏

  - **M1.A.1 暴露的"第 11 份文件"问题**: spec 列出 sync-state.json 是 11 份顶层之一,但代码未实现 → 11 份变 10 份 + 1 个孤儿在根

  - **本次同根因家族**: N100(文件损坏) + N101(状态不诚实) + N105(hook 透传) + **N106(路径漂移)**

- **Related**: failure-modes N106, lessons/N106-sync-state-path.md (新), sync_ai_memory.py SYNC_STATE 常量 + update_sync_state 函数, spec.md §5 完整目录树, M1.A.1 任务 (11 份顶层补全部)



---



## #49 M2.D — pre-commit stages 治理缺位 (2026-06-17 M2.D 闭环)



**问题**

- pre-commit config 把 12 hook 全放 `pre-commit` stage 串行跑 → 60-90s 慢 + ruff 215 historical errors + mypy executable 缺失 → 必失败

- lint 4 hook (eslint/prettier/ruff/mypy) 与 GAF 10 fast hook 混跑, 浪费本地 commit 时间

- AI 跑 commit 必失败 → 默认 `--no-verify` 跳过 (违反 N105 精神)

- CI / 本地无法差异化跑 fast vs slow hook, 测试反馈慢



**根因 (M2.D 实战提取)**

1. **stages 字段未用**: pre-commit 框架支持 `stages: [pre-commit, manual]`, 但 v8.3.1 没用, 全混跑

2. **lint hook 阻塞治理 hook**: 4 lint hook 失败 → 10 GAF hook 跑不到, 治理断链

3. **历史欠债**: backend/agent 历史代码有 ruff 215 errors, 没清理 + 加 lint hook → 永久阻塞

4. **mypy executable 缺失**: hook 配置没 `language: system` 兼容, 装 mypy 后才能跑



**关键修复 (M2.D 闭环)**

- `.pre-commit-config.yaml`: 4 lint hook 加 `stages: [manual]`, 10 GAF fast hook 留 pre-commit stage

- `docs/architecture/cross-cutting/pre-commit-stages.md`: 132 行使用文档 (stage 划分 / 跑法 / CI 集成 / 故障排查)

- 本 commit: `-`

- 验证: `pre-commit run --all-files` 10 fast hook 全 Passed, exit 0



**AI 必做 (M2.D stage 分层硬规则)**

- ✅ 加新 hook 时考虑 stage 归属: fast (sync/check) → pre-commit; slow (lint) → manual

- ✅ 本地 commit 不阻塞: `git commit -m "..."` 自动跑 fast hook (< 5s)

- ✅ 手动跑 lint: `pre-commit run --hook-stage manual` 或 `--all-files`

- ✅ CI 集成: 2 步跑 (fast + manual) 完整验证

- ✅ `stages` 字段写在 hook 内, 不能写在 repo 顶层 (YAML 解析错)

- ❌ NEVER 把 slow hook 放 `pre-commit` stage 阻塞 commit

- ❌ NEVER 改 stages 字段写错位置 (顶层 hooks 列表下)

- ❌ NEVER 跑 `pre-commit run --all-files` 不带 `--hook-stage manual` 跑 lint (会全跑)



**反模式家族**

- N82 + N100 + N101 + N105 + N106 + N110 + N111 + N114 + N116 + N117 + N118 + N91 + N119 + **M2.D (本条 pre-commit stages 治理缺位)** — 同根因 (工具调用治理缺位)

## 47. Vite Dev Proxy `localhost` Causes WebSocket Handshake Failures

**问题**: Browser reports `WebSocket handshake: Unexpected response code: 500` for `/ws/dashboard/` and `/ws/notifications/` through Vite dev proxy, while direct `ws://127.0.0.1:8000/ws/.../` works.

**根因**: `vite.config.ts` used `ws://localhost:8000` as proxy target. On Windows `localhost` may resolve to IPv6 `::1` while Django `runserver` binds to IPv4 `127.0.0.1`, so Vite forwards the upgrade to the wrong socket.

**修复**:
- commit `-`: change Vite proxy targets to `127.0.0.1:8000` for both `/api` and `/ws`

**预防**:
- ✅ Dev proxy targets must use explicit `127.0.0.1` loopback to avoid IPv4/IPv6 ambiguity
- ✅ When debugging WS handshake errors, test direct backend IP connection first

**关联**:
- `.ai-memory/_archive/lessons-retired/N139-vite-proxy-localhost-ws-handshake.md`
- `frontend/vite.config.ts`
- `frontend/src/websocket/client.ts`
- `frontend/src/hooks/useNotificationWebSocket.ts`

---