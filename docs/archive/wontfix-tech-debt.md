---
summary: 不修复/已失效/已评估技术债务清单 — ❌ WONTFIX / ❌ INVALIDATED / ❌ EVALUATED 条目
applies_to: [project]
last_updated: 2026-08-23 (TD-391 重编号闭合)
---

# Won't Fix / Invalidated / Evaluated Tech Debts

> 本文件包含所有 ❌ WONTFIX / ❌ INVALIDATED / ❌ EVALUATED 状态的技术债务条目。
>
> **来源**：从 `tech-debt-register.md` 拆分而来（2026-07-10）。

---

## TD-329: spec-49 红线全脚本化 ❌ INVALIDATED (TD-318 已覆盖全部范围)

- **状态**: ❌ INVALIDATED (2026-07-22, TD-318 实际实现已覆盖 TD-329 全部范围)
- **优先级**: P2 → ❌ INVALIDATED
- **登记时间**: 2026-07-21
- **评估时间**: 2026-07-22
- **来源**: 2026-07-21 AI 思维链/工作流/规则文档三维评估报告 P2
- **维度**: 工作流
- **问题**: spec-49 红线 (连续 ≥3 个 patch 失败停下 / 连续 ≥5 个 patch 成功后停下 / 每 10 个 patch 后停下报告进度) 完全依赖 AI 自觉计数, 无 automated counter; TD-318 解决 3 次失败计数器, 本 TD 解决 5 次成功 + 10 个 patch 节点
- **invalidated 理由** (2026-07-22 验证):
  1. **TD-318 实际实现已覆盖全部 3 counter**: `doc_health_consumed.py` L72-74 已有 `consecutive_failures` + `consecutive_successes` + `total_patches_this_session` 三个 counter, 非 TD-329 描述的 "TD-318 只解决 3 次失败计数器"
  2. **should_stop_and_report() 已检查 2 红线**: L440-454 已实现 `consecutive_failures >= 3` (红线 1) + `consecutive_successes >= 5 AND total_patches_this_session % 10 == 0` (红线 2), 正是 TD-329 提出的 "3 条件检查"
  3. **11 tests 全通过**: `test_doc_health_consumed_spec49.py` 已有 11 tests 覆盖所有条件触发 + 重置 + 持久化 (test_should_stop_after_3_consecutive_failures + test_should_stop_at_10_patches_with_5_consecutive_successes + test_should_not_stop_under_threshold + test_reset_session_clears_total_patches 等), 超 TD-329 要求的 "6+ tests"
  4. **§0.5 红线文档已更新**: `gaf-orchestrator/SKILL.md` L74-75 已含 2 条 spec-49 红线描述 ("连续 ≥3 个 patch 失败 → 必须停下报告用户" + "连续 ≥5 个 patch 成功 → 每 10 个 patch 后停下报告进度")
  5. **TD-329 描述与 TD-318 实际实现不符**: TD-329 登记时基于 "TD-318 只解决 3 次失败计数器" 的假设, 但 TD-318 实际实现已涵盖全部 3 counter + 2 红线检查 + 11 tests, TD-329 范围 100% 被覆盖
- **验证命令**:
  - `conda run -n gaf python -m pytest scripts/tests/test_doc_health_consumed_spec49.py -v` → 11/11 passed
  - `grep -n "consecutive_successes\|total_patches_this_session" scripts/governance/doc_health_consumed.py` → L73-74 (已存在)
  - `grep -n "should_stop_and_report" scripts/governance/doc_health_consumed.py` → L423 (已存在, 2 红线检查)
- **关联文件**: scripts/governance/doc_health_consumed.py (TD-318 实现), scripts/tests/test_doc_health_consumed_spec49.py (TD-318 11 tests), .trae/skills/gaf-orchestrator/SKILL.md (§0.5 红线文档 L74-75)
- **关联 TD**: TD-318 (spec-49 红线脚本强制, 已 ✅ FIXED, 实际覆盖 TD-329 全部范围)

---

## TD-328: gaf_init.sh 重写为 Python ❌ WONTFIX (与 TD-320 互斥, PowerShell 已交付, EVALUATED)

- **状态**: ❌ WONTFIX (EVALUATED, 2026-07-22)
- **优先级**: P2 → ❌ WONTFIX
- **登记时间**: 2026-07-21
- **评估时间**: 2026-07-22
- **来源**: 2026-07-21 AI 思维链/工作流/规则文档三维评估报告 P2
- **维度**: 工作流
- **问题**: gaf_init.sh 是 bash-only, 依赖 Unix 工具 (wc/grep/awk), Windows 需 git bash; 与 TD-320 (gaf_init.ps1) 互补, 但根本解法是重写为 Python 消除 bash 依赖
- **影响**: 跨平台兼容性受限; bash 语法在 Windows 环境需额外工具
- **wontfix 理由** (2026-07-22 评估):
  1. **与 TD-320 互斥**: TD-320 已于 2026-07-21 spec-82 交付 PowerShell 等价版本 (gaf_init.ps1 + conda 自动发现 + README.md 入口说明), bash-only 跨平台问题已解决
  2. **3 平台已覆盖**: Linux/macOS 用 .sh (bash 原生), Windows 用 .ps1 (PowerShell 7.x 原生), 无剩余平台缺口
  3. **Python 重写收益小**: 主要收益 (跨平台) 已被 TD-320 实现; 剩余收益 (单一源码) 边际价值低
  4. **Python 重写成本高**: 重写 ~300 行 bash 逻辑 + conda subprocess 激活复杂 (PowerShell hook 等价物需重新实现) + test_gaf_init.py 新建 + project_rules §1 和 gaf-orchestrator/SKILL.md 引用同步
  5. **双轨维护成本可接受**: .sh 和 .ps1 已通过 v9.0 同步设计 (相同 §编号结构), 新增逻辑 (如 §3.7.2 N181 警告) 已证明可同步更新; TD-324 spec-86 实测两文件同步加段无负担
- **保留方案**: 保留 .sh/.ps1 双轨, 不重写 Python; 后续新增 gaf_init 逻辑时同步更新两文件 (已有惯例)
- **关联文件**: scripts/gaf_init.sh, scripts/gaf_init.ps1 (TD-320 交付), .trae/rules/project_rules.md, .trae/skills/gaf-orchestrator/SKILL.md
- **关联 TD**: TD-320 (PowerShell 等价版本, 互斥项, 已 ✅ FIXED)

---

## TD-322: spec 编号归一 (同号多版本歧义) ❌ WONTFIX (spec-84 方案 B: 索引脚本 + pre-commit hook mitigation)

- **状态**: ❌ WONTFIX (spec-84 方案 B, 2026-07-21)
- **优先级**: P1 → ❌ WONTFIX
- **登记时间**: 2026-07-21
- **评估时间**: 2026-07-21 (spec-84 方案评估)
- **来源**: 2026-07-21 AI 思维链/工作流/规则文档三维评估报告 P1
- **维度**: 工作流
- **问题**: spec-36/38/39/41/42/43/44/45 各有 2 个不同主题文件 (8 组 16 文件), 同 spec 号被复用为不同主题, 引用时 "spec-36" 指代不清, 有歧义风险
- **影响**: 检索 spec 引用时无法确定具体文件; N176 hash 回填时 spec-NN 引用歧义
- **wontfix 理由** (spec-84 方案评估):
  1. **任务规模失衡**: 16 文件重命名 + 200+ 处引用更新 (active/fixed/wontfix/lessons/evidence/specs/plans) vs TD-322 收益 (消除"潜在歧义", 非现存 bug)
  2. **git blame 污染**: 大量引用更新 commit 会污染文件历史, 影响后续考古
  3. **evidence 完整性**: `.ai-memory/evidence/2026-07-20-spec42-self-evolution-flywheel/` 等目录名改动后, N176 hash 回填会混乱
  4. **上下文消歧**: 现有引用虽用 spec-NN 简写, 但周围通常有日期/主题/commit hash 上下文, 实际歧义可消解
  5. **治本优先**: 索引脚本 + pre-commit hook 防止新增冲突, 比追溯历史更值得
- **mitigation** (spec-84 方案 B 实施):
  - **新建 `scripts/governance/sync_spec_index.py`**: 扫描 `.trae/specs/*.md` frontmatter `spec_id:` + `commit:` 字段, 生成 `.ai-memory/spec-index.md` 索引表 (spec_id | 文件名 | 标题 | commit | 日期 | 来源); `--check` 模式检测同号多版本 WARN
  - **新建 `scripts/hooks/check_spec_id_collision.py`**: pre-commit hook, 检测 staged spec 文件 spec_id 是否与已有冲突; 冲突 → exit 1 + 4 步修复提示 (用 spec-NN-a/b 后缀 / 下一个空闲 spec-NN / 查索引 / 历史 wontfix 说明)
  - **新建 `scripts/tests/test_sync_spec_index.py`** (9 tests): parse_frontmatter / extract_from_filename / scan_specs / detect_collisions / render_index / render_collisions / hook 无 staged / hook --force / integration 真实 repo 8 组 16 文件冲突
  - **注册 `gaf-spec-id-collision` hook** 到 `.pre-commit-config.yaml` (pre-commit stage, 在 `gaf-b2-evidence` 之后)
  - **生成 `.ai-memory/spec-index.md`**: 70 个 spec 索引 + 8 组 16 文件冲突 WARN 段
- **wontfix 决策**: 现有 8 组 16 文件历史同号多版本保留不动 (历史文件不重命名, 引用不更新); 新增 spec 强制 spec_id 唯一 (hook 阻止新增冲突)
- **关联文件**:
  - `scripts/governance/sync_spec_index.py` (新建, ~260 行)
  - `scripts/hooks/check_spec_id_collision.py` (新建, ~180 行)
  - `scripts/tests/test_sync_spec_index.py` (新建, ~170 行, 9 tests)
  - `.pre-commit-config.yaml` (注册 `gaf-spec-id-collision` hook)
  - `.ai-memory/spec-index.md` (新建, 自动生成的 spec 索引)
  - `.trae/specs/2026-07-21-spec84-td322-spec-id-disambiguation.md` (评估 spec)

---

## TD-290 — agent coord_transformer per-monitor detection TODO ❌ EVALUATED

- **状态**: ❌ EVALUATED (审计后确认当前实现工作正常, 多显示器 fullscreen 是后续 feature)
- **优先级**: P3
- **登记时间**: 2026-07-20
- **评估时间**: 2026-07-20 (spec-39)
- **来源**: spec-53 commit (`-`) 后 L3-1 轻量扫描 [B] 类 (维度 ② 代码层)
- **症状**: `agent/src/utils/coord_transformer.py:114` TODO 注释 "replace with proper per-monitor detection using MonitorFromWindow + GetMonitorInfo when fullscreen support lands"
- **评估结论**:
  - 当前实现用 `display_builder` 比较 client rect 设置 `display_id`, 在单显示器 + 多显示器窗口化场景下工作正常
  - 多显示器 fullscreen 场景 (窗口 fullscreen 在副屏) 坐标转换可能不准 — 但这是 BD2-AUTO 也未完全解决的边界场景
  - GAF 当前不支持 agent 主动 multi-monitor fullscreen (用户场景都是单显示器或窗口化), 不触发该 TODO
  - 该 TODO 是 "when fullscreen support lands" 触发条件, 不是 "现在就修"
- **wontfix 理由**: 当前实现工作; 多显示器 fullscreen 是后续 feature (不在当前 agent scope); 该 TODO 是 feature 触发条件而非 bug
- **重新开放条件**: 当 agent 支持 multi-monitor fullscreen 时 (独立 feature spec), 同步实现 per-monitor detection
- **evidence**: spec-39 审计 (`grep "TODO" agent/src/utils/coord_transformer.py` 命中 2 处)
- **commit**: spec-39

---

## TD-276 — executions list N+1 query 风险 ❌ EVALUATED

- **状态**: ❌ EVALUATED (审计后确认无 N+1, 循环只访问 FK _id 字段不触发 DB)
- **优先级**: P3
- **登记时间**: 2026-07-20
- **评估时间**: 2026-07-20 (spec-39)
- **来源**: spec-53 commit (`-`) 后 L3-1 轻量扫描 [B] 类 (维度 ⑦ 数据层)
- **症状**: `backend/executions/views.py` 中 `ExecutionStep.objects.filter(...)` 循环访问 `s.execution_id` 怀疑 N+1
- **评估结论**:
  - 审计 `executions/views.py` 实际循环代码: 只访问 `s.execution_id` (FK _id 字段, 不查 DB) 和 `s.started_at`/`s.completed_at`/`s.status` (本地字段)
  - **未访问** `s.execution.xxx` (FK 跳转, 触发 DB 查询)
  - Django ORM 中 `_id` 后缀字段是直接存储的 FK 值, 不触发 DB; 只有访问 `s.execution` (无 _id 后缀) 才触发 FK 跳转查询
  - 验证: `grep "s\.execution[^_]" backend/executions/views.py` = 0 处, 确认无 FK 跳转
- **wontfix 理由**: 不是 N+1; 循环只访问本地字段 + FK _id, 不触发 DB; 无需 select_related/prefetch_related
- **重新开放条件**: 若未来该循环改为访问 `s.execution.<field>`, 立即加 select_related('execution')
- **evidence**: spec-39 审计 (`grep "s\.execution[^_]" backend/executions/views.py` = 0)
- **commit**: spec-39

---

## TD-271 — 响应式设计缺失 (5 页面审计) ❌ EVALUATED

- **状态**: ❌ EVALUATED (审计后确认已用其他方式实现响应式, 不需显式 Col 断点)
- **优先级**: P2
- **登记时间**: 2026-07-19
- **评估时间**: 2026-07-20 (spec-36 Phase 3)
- **来源**: spec-35 L3-1 全量扫描 [B] 类 (维度 ④ 界面层)
- **症状**: 多页面缺 `<Col xs={...} sm={...} md={...}>` 响应式断点, 平板/手机宽度下布局塌陷
- **评估结论**: 5 个"缺响应式"页面 (Tasks/index, Resources/index, Accounts/GameAccountsPage, Ops/Executions/index, System/SystemSettings) 审计后发现已用其他方式实现响应式:
  - Table 主页面: Table 自带 `scroll: { x: 'max-content' }` 横向滚动 + 列宽自适应, 不需 Col 断点
  - 操作按钮/搜索筛选: 已用 `gaf-flex-wrap` 让小屏幕换行
  - Form 主页面 (SystemSettings): `maxWidth: 600` 限制宽度, 小屏幕自适应
- **评估证据**:
  - `grep "gaf-flex-wrap" frontend/src/pages/Accounts/GameAccountsPage.tsx` = 2 处 (L304/L339)
  - `grep "gaf-flex-wrap" frontend/src/pages/Tasks/index.tsx` 命中
  - `grep "gaf-flex-wrap" frontend/src/pages/Ops/Executions/index.tsx` 命中
  - SystemSettings 用 `<div style={{ maxWidth: 600 }}>` 限制宽度
  - Resources/index 用 Tabs + Table, Table 自带响应式
- **wontfix 理由**: TD-271 登记时的"缺响应式"是误判 — 没有显式 Col 断点不等于不响应式, flex-wrap + Table 横向滚动 + maxWidth 都是合法的响应式方案
- **evidence**: spec-36 Phase 3 审计报告
- **commit**: -

---

## TD-001 — WGC 截图 `E_NOINTERFACE` ❌ WONTFIX

- **症状**：`WGC 初始化失败: RoGetActivationFactory(interop) 失败: 0x80004002`
- **根因（深度调查后确认）**：
  1. **Windows 11 24H2 (build 26200) 上 WGC factory 的 IID 布局已变更**：
     - 通过 `IInspectable::GetIids` 枚举，`Windows.Graphics.Capture.GraphicsCaptureItem` factory 实际只支持 3 个 IID：`{00000035-0000-0000-C000-000000000046}`、`{a87ebea5-457c-5788-ab47-0cf1d3637e74}`、`{3b92acc9-e584-5862-bf5c-9c316c6d2dbb}`
     - **均不匹配**文档中的 `IGraphicsCaptureItemInterop` IID `{3628E81B-3C70-4C5C-8F20-8E9E4F08BF15}` 或 `IGraphicsCaptureItemStatics` IID `{5F9A6EC0-7D76-11E9-A3FC-00155D3E8ED6}`
     - `RoGetActivationFactory(hstring, IID_IGraphicsCaptureItemInterop, ...)` 永远返回 `E_NOINTERFACE`
  2. **未知 IID 在公开资料中无文档**：网络搜索这 3 个 IID 无任何匹配，windows-rs 文档只列旧 IID
  3. **不是 argtypes 问题**：测试已排除 — 即使设置 `combase.RoGetActivationFactory.argtypes` 正确传递 64 位 HSTRING 指针，仍返回 E_NOINTERFACE
  4. **不是 Windows 版本问题**：系统是 Windows 11 24H2 build 26200，远超 WGC Win32 互通所需的 19041+ (2004)
  5. **factory 本身存在且可访问**：QI for `IUnknown`/`IInspectable` 成功，`GetRuntimeClassName` 返回 `Windows.Graphics.Capture.GraphicsCaptureItem`
- **影响**：WGC 不可用，但 PrintWindow (TD-003 ✅) + DXGI (TD-002 ✅) + GDI 三个截图方法已工作正常，不阻塞任何场景
- **WONTFIX 理由**：
  1. 修复需逆向 Win11 24H2 的 3 个未知 IID，工作量大且无公开文档
  2. 即使识别出 IID，新接口可能用 `TryCreateFromWindowId(WindowId)` 而非 `CreateForWindow(HWND)`，需重新设计 API 调用层
  3. Microsoft Q&A 官方答复：Win32 应用做截图推荐 GDI/PrintWindow，WGC 仅在实时视频捕获场景才有优势
  4. 收益有限：WGC 比 PrintWindow 略快，但本项目的截图频率（每秒≤1帧）下无显著差异
  5. 按 §6.5 "禁止把修不了的 debt 留在 🔧 状态超过 3 轮" — 标 ❌ WONTFIX 而非继续积压
- **重新开放条件**：
  - 若未来需要 60+ FPS 实时视频捕获（PrintWindow/DXGI 不够用）
  - 或 Microsoft 重新发布 Win32 WGC interop 文档
  - 或社区有人逆向出 Win11 24H2 的新 IID 布局
- **登记时间**：2026-07-04
- **WONTFIX 决策时间**：2026-07-05

---

## TD-010 — Backend 截图帧转发层未 dedup（dashboard 收重复帧） ✅ INVALIDATED

- **症状（原始报告）**：TD-009 修复后端到端验证称 agent 发 2 帧 → dashboard 收 41 帧，疑似 backend 转发层倍增。
- **复现验证（2026-07-06，决定性测试）**：写脚本模拟 agent 通过 `ws/protocol/agents/` 发送 1 个合法 screenshot.frame（UUID trace_id + 标准 frame schema + 1x1 PNG），同时监听 `ws/dashboard/`：
  - 发送 1 帧 → dashboard 收到 **1 帧**（trace_id 匹配）
  - backend `_handle_screenshot_frame` 被调用 1 次（调试 log 记录 1 条）
  - 结论：**backend `group_send` → `FrontendConsumer.screenshot_frame` 链路 1:1 转发，无倍增**
- **根因（原始误判）**：原始"agent 发 2 帧 / dashboard 收 41 帧"无法复现。复核 agent2.log：
  - agent 实际通过 WebSocket 发送的 `> TEXT screenshot.frame` = **0 条**（"Future 已调度" 6 次但 send 未落地到 WS）
  - backend 调试 log 在自然运行中从未生成，证明 backend 从未收到过 agent 的 screenshot.frame
  - 原始"41 帧"疑为 test_dedup.py 客户端 request_screenshot_stream 保活/重连副作用或观测窗口错位，非 backend 倍增
- **结论**：TD-010 **非 bug**，backend 转发层无需 dedup（1:1 转发）。TD-009 agent 端 dedup 已足够。
- **遗留（独立问题，非 TD-010）**：
  - agent LDPlayer 截图异常：ldopengl64.dll 每秒重新加载，capture 失败循环（阻塞帧产出）
  - agent "Future 已调度"后 send 未落地到 WS（6 次调度 0 次成功 `> TEXT`）
- **登记时间**：2026-07-06
- **失效时间**：2026-07-06（决定性复现测试证明非 bug）
- **发现于**：TD-009 修复后端到端验证（原始观测误判）

---

## TD-017 — sync_skills.py 漏校验 _shared/decision-tree.md ❌ INVALIDATED

> **失效说明** (2026-07-07 gaf-restructure-execution Stage 3 复核): Glob 验证 `.trae/skills/_shared/*` 返回 `No file found`, 实际不存在 `_shared/decision-tree.md` 文件, 只有 `_shared/decision-tree-changelog.md` (changelog 不需要 sync_skills 校验). TD-017 描述基于错误的 stage-2 评估, 实际决策树副本数 = 4, sync_skills.py 当前行为正确, 无需扩展校验范围. 标记为 ❌ INVALIDATED, 不再处理.

- **症状**：(原描述) `sync_skills.py --check` 报告 "✅ 4 skills + 1 rule 副本一致"，但实际存在第 5 份决策树副本 `.trae/skills/_shared/decision-tree.md`...
- **复核结论**：描述错误，`_shared/decision-tree.md` 不存在，4 份副本是完整的
- **何时修**：不修（已失效）
- **登记时间**：2026-07-07
- **失效时间**：2026-07-07（gaf-restructure-execution Stage 3）
- **发现于**：gaf-restructure-foundation Stage 2 Task 11（决策树 skill 引用映射）

---

## TD-046 — `tasks/migrations/` 累积 40 个 migration ❌ EVALUATED (squash 不可行)

- **症状**：`backend/tasks/migrations/` 已累积 40 个 migration 文件（0040_remove_tracespan），是所有 app 中最多的（其他 app 通常 1-6 个）。
- **根因**：tasks app 承载 29 个模型，模型变更频繁；重复模型迁移（如 CrashReport TD-035）和 Stage 7 越界模型迁移（AlertRule/TaskChain/FeatureFlag/TemplateEffectiveness/AuditLog/AppSettings/GameProfile 7 个模型迁移各产生 1-2 个 migration）进一步增加 migration 数量。
- **影响**：新环境 `migrate` 命令执行时间长；migration 历史冗长，难以追溯模型演变；重复模型迁移产生冗余 migration（如 tasks.CrashReport 的 create + delete）。
- **修复方案**：归一化完成后（TD-021/TD-039），评估是否 squash migration（`python manage.py squashmigrations tasks 0037`）；或保留历史 migration 不动（squash 有风险）。
- **实际评估（2026-07-10）**：执行 `squashmigrations tasks 0040` 生成 `0001_squashed_0040_remove_tracespan.py`，手动移植 0021 的 RunPython 函数后运行 `migrate --plan` 触发 `CircularDependencyError: tasks.0001_squashed_0040_remove_tracespan, scheduler.0003_phase5_bindings, scheduler.0004_phase6_unattended_scheduler, scheduler.0005_alter_deviceresourcemapping_device, scheduler.0006_delete_deviceresourcemapping`。
  - **根因**：`scheduler.0003_phase5_bindings` 依赖 `tasks.0013`，而原 `tasks.0014_phase5_bindings` 依赖 `scheduler.0003`。原 migration 序列通过交错解决依赖（tasks.0013 → scheduler.0003 → tasks.0014），squash 将 tasks.0013 和 tasks.0014 合并为一后，交错被扁平化为循环依赖。
  - **3 个下游 app 依赖**：`tracing.0001`→`tasks.0040`、`pipeline.0004`→`tasks.0038`、`pipeline.0005`→`tasks.0039`，squash 后需全部更新。
  - **决策**：squash 需拆分 squashed migration 在依赖边界处（tasks.0013 | scheduler.0003 | tasks.0014-0040）或重构 scheduler migrations 消除交叉依赖，风险 > P3 收益。保留历史 migration 不动。
- **验证标准**：评估后决定 squash 或保留；如 squash，migration 文件数减少且 `migrate` 行为不变。
- **何时修**：2026-07-10（评估完成，决定保留历史）
- **登记时间**：2026-07-07
- **发现于**：gaf-restructure-foundation Stage 3b 评估（`docs/architecture/backend-app-consolidation-evaluation.md` §8.1）

---

## TD-085 — Agent 截图流 1s 间隔 subprocess 风险 ❌ WONTFIX

- **状态**: ❌ WONTFIX
- **优先级**: P2
- **登记时间**: 2026-07-11
- **评估时间**: 2026-07-13
- **症状**: `agent/src/client/handler.py:729` 截图流循环 1s 间隔，遍历所有设备调用 `device.capture()`。当 ldopengl 不可用时 fallback 到 `adb exec-out screencap`，每秒 N 个 subprocess（N=设备数）
- **根因**: 截图流设计为实时性需求（1s 帧间隔），但未考虑 ADB subprocess fallback 的开销
- **影响**: 多设备时形成 subprocess storm，与 N154 同类反模式
- **评估结论**: N154 修复时已加 ThreadPoolExecutor 并行优化（`max_workers = min(4, len(devices))`，最多 4 个并行 subprocess）。ADBDevice 降级链优先用原生 API（nemu→scrcpy→DroidCast→u2），ADB screencap 是最后手段。风险从"N 个 subprocess/秒"降低到"最多 4 个 subprocess/秒"，可接受。如果原生 API 不可用，应修复环境配置而非降低帧率。
- **关联**: N154 (`lessons/2026-07-11-n154*`)
- **迁移记录**: 从 active.md 迁入（S5 任务 6，2026-07-14）

---

## TD-174 — Trae IDE 对话上下文压缩丢失 L3 评估明细 ❌ WONTFIX

- **状态**: ❌ WONTFIX (平台限制)
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: spec 2026-07-17-ai-docs-round3-cleanup.md Phase 5 验收 — 2 [C] 类登记 wontfix.md
- **症状**: 3 agent 并行评估输出 18 [A] + 17 [B] + 2 [C] 分级明细, spec 创建时仅保留 18 [A] 项, 17 [B] + 2 [C] 项明细在对话上下文压缩中丢失。后续 Phase 5 登记 tech-debt 时无法精确恢复 [B]/[C] 项原始内容, 仅能基于 Phase 1-4 执行观察重新构造 (TD-157 / TD-170 同根因)。
- **根因**: Trae IDE 对话上下文窗口有限, 接近上限时自动压缩历史消息, 长会话中的评估明细 (尤其是非 [A] 类次要项) 容易被压缩丢失。
- **影响**: L3 评估的 [B]/[C] 项无法在后续阶段精确恢复, 可能导致重复发现同一问题 (TD-157 已记录此影响)。
- **WONTFIX 理由**:
  1. 根因是 Trae IDE / LLM 平台层限制, 非 GAF 项目代码可修复
  2. N160 已规定 ≥ 15 轮新开对话 + §4.10 spec 分阶段协议缓解上下文压力, 但单次会话内压缩仍不可避免
  3. spec 模板已要求保留 [A] 项明细 (本 spec 已遵照), [B]/[C] 项可接受在 active.md / wontfix.md 重新登记
- **缓解措施** (已在 spec 模板中):
  - spec 创建时同步登记 [B] 项到 active.md (本 spec Phase 5 已补登记 TD-157~TD-173)
  - [C] 项同步登记到 wontfix.md (本条 + TD-175)
- **重新开放条件**: Trae IDE 支持无限上下文窗口或评估明细自动持久化到文件
- **关联**: TD-157 (17 [B] 项汇总), TD-170 (spec 未保留 [B] 项明细), N160 (上下文预算管理), §4.10 (spec 分阶段协议)

---

## TD-175 — ruff 工具对 .sh 脚本按 Python 解析报 syntax errors ❌ WONTFIX

- **状态**: ❌ WONTFIX (工具边界)
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: spec 2026-07-17-ai-docs-round3-cleanup.md Phase 5 全量回归 — ruff check scripts/gaf_init.sh
- **症状**: `conda run -n gaf ruff check scripts/gaf_init.sh` 报大量 Python syntax errors (expected indented block / invalid syntax 等), 但 `gaf_init.sh` 是 bash 脚本, 不符合 Python 语法是预期行为。`ruff check --select=E9,F63,F7,F82 scripts/gaf_init.sh` 关键错误检查通过 (0 errors)。
- **根因**: ruff 工具设计上仅支持 Python 文件解析, 默认对所有传入文件按 Python AST 解析, .sh / .yaml / .md 等非 Python 文件会触发 syntax errors。这是 ruff 工具的设计边界, 非 GAF 项目代码问题。
- **影响**: pre-commit hook 的 ruff manual stage 若包含 .sh 文件会报错 (不阻塞 commit, manual stage 需显式触发)。CI 跑 manual stage 时需注意排除非 Python 文件。
- **WONTFIX 理由**:
  1. 根因是 ruff 工具设计边界, 非 GAF 项目可修复
  2. ruff upstream 明确声明仅支持 Python 文件 (https://docs.astral.sh/ruff/)
  3. workaround (pyproject.toml `extend-exclude = ["*.sh"]`) 可缓解但非根因修复, 且 ruff 默认就不应被传非 Python 文件
  4. 现有 pre-commit hook 已通过 `language: system` + 显式文件类型过滤避免此问题
- **缓解措施** (已生效):
  - pre-commit ruff hook 使用 `types: [python]` 仅传 Python 文件
  - 手动跑 ruff 时用 `--select=E9,F63,F7,F82` 仅查关键错误, 或显式指定 .py 文件
- **重新开放条件**: ruff upstream 支持非 Python 文件解析, 或迁移到支持多语言的 linter (如 biome)
- **关联**: TD-156 (ruff 4 处预存错误, 已登记 active.md), §3.3 N150 (pre-commit 失败根因修复)

---

## TD-254 — brainstorming skill 不在 gaf-* skills 引用 ❌ WONTFIX

- **状态**: ❌ WONTFIX (设计决策)
- **优先级**: P3
- **登记时间**: 2026-07-18
- **来源**: R7 评估 P2-2 — brainstorming skill 在 gaf-* skills 0 引用
- **症状**: brainstorming skill (superpowers) 在 5 个 gaf-* SKILL.md + project_rules.md + .ai-memory/ 中均 0 引用
- **WONTFIX 理由**:
  1. superpowers-zh §边界声明 §2 明确"不重复定义: GAF 项目特定规范在 docs/standards/ 中独立维护, 不复制 superpowers 的通用内容"
  2. brainstorming 的核心能力 (探索意图 / 产出方案 / 用户批准) 在 GAF 体系已有功能等价物: §0.5 step_5 (A/B/C 备选方案) + §0.5 step_8 (Plan 批准) + refactor 分支 step_4_plan
  3. brainstorming 的 HARD-GATE (用户批准前不得写代码) 与 §3.6 (计划内任务 AI 完全自治, 不问"是否开始") 存在根本冲突
  4. AI 在大修改场景可按 superpowers-zh §2 "重叠场景处理" 按需加载 brainstorming, 无需硬挂载
- **重新开放条件**: 若实践中发现 new_feature 中修改以上场景确实缺少"设计探索"环节且现有 §0.5 流程不足以覆盖
- **关联**: superpowers-zh.md §边界声明, project_rules.md §0.5 + §3.6

---

## TD-255 — N166 不进 arch-mistakes.md ❌ WONTFIX

- **状态**: ❌ WONTFIX (性质不符)
- **优先级**: P3
- **登记时间**: 2026-07-18
- **来源**: R7 评估 P3-5 — N166 在 arch-mistakes.md 缺独立条目
- **症状**: N166 (L3 持续评估循环 + 沉淀纪律) 在 .ai-memory/summaries/architecture-mistakes.md 中仅在 N167 条目"同根因家族"行被弱引用, 无独立章节
- **WONTFIX 理由**:
  1. N166 的 `category: workflow` (lesson frontmatter 明示), 触发原话是工作流要求, 内容是 L3 循环 + 沉淀纪律, **不属于架构反模式**
  2. arch-mistakes.md frontmatter `symptom: [architecture, design, mistake, history]` 自我定位为架构错误清单, N166 不符合
  3. §6.2 L1 子分级明确"5 层全分发"触发条件是"新架构反模式 / 新 N## / > 15 行 / 跨层影响", N166 性质是"新流程环节" (L1-中档), 不满足 L1-大触发条件
  4. N166 已有 4 层分发 (lesson + failure-modes 索引 + 2 个 yn-matrices sections + project_rules 3 个章节 + ai-operating-handbook Part 2), 分发已充分
  5. 若为追求分发层数将工作流类教训塞入 arch-mistakes, 会破坏该文件作为架构反模式权威源的职责单一性
- **重新开放条件**: 若 N166 性质从工作流模式转变为架构反模式 (如发现 L3 扫描清单的架构维度本身是架构错误)
- **关联**: N166 lesson, .ai-memory/summaries/architecture-mistakes.md N167 条目同根因家族行

---

## TD-127 — ruff 剩余 60 处命名规范/风格类 errors ❌ WONTFIX (partial fix)

- **状态**: ✅ FIXED (部分) + ❌ WONTFIX (剩余 60 处)
- **优先级**: P3
- **登记时间**: 2026-07-16
- **修复时间**: 2026-07-18 (TD-127 Phase 2 — backend/ + agent/ ruff errors)
- **来源**: N166 L3-1 扫描 — 月度健康检查 [I3] Ruff errors 批量修复后剩余
- **修复总结 (2026-07-18)**:
  - 原 152 errors → 修复后剩余 60 errors (减少 92 处, 60.5%)
  - **pyproject.toml 配置**: 加 `[tool.ruff.lint.per-file-ignores]` 段 — `"__init__.py" = ["F401"]` (re-export 豁免) + `"agent/src/recognition/cache.py" = ["F401"]` (cv2 try/except 检测豁免)
  - **ruff --fix --unsafe-fixes 自动修复 56 处**: I001 (unsorted-imports) / UP007 (Union → X|Y) / UP031 (printf-string) / UP035 (typing.List → list) / F401 (dccache.py 未用 Any) / F841 (unused-variable, 12 处) / B905 (zip-without-explicit-strict, 4 处) / C408 (unnecessary-collection-call, 1 处) / SIM102/SIM108/SIM118 等
  - **手动修复 7 处**: ① `agent/src/recognition/ocr/__init__.py` 删除未用 `from typing import List`; ② `agent/src/engine/target.py` 把 `Union[...]` 改为 `X | Y` (PEP 604); ③ `agent/src/utils/screenshot_diagnostic.py:42,44` 加 `# noqa: E402`; ④ `agent/tests/test_engine_structured_log_integration.py:20,21` 加 `# noqa: E402`
- **剩余 60 处 wontfix 分类** (ruff check backend/ agent/ --statistics 2026-07-18):
  - **命名规范类 (43 处)** — 改名会破坏现有 API 契约 / 前端字段映射 / 第三方对接:
    - 23 N806 (non-lowercase-variable-in-function) — 多为 DRF serializer 字段 / Win32 API 常量映射
    - 12 N801 (invalid-class-name) — 业务领域类名 (如 PvP/GvG 等游戏术语缩写)
    - 4 N802 (invalid-function-name) — 测试方法 / Win32 API 包装方法
    - 3 N816 (mixed-case-variable-in-global-scope) — 模块级常量与第三方库对齐
    - 1 N814 (camelcase-imported-as-constant)
  - **风格类 (17 处)** — 改动收益低, 部分会降低可读性:
    - 12 SIM117 (multiple-with-statements) — 嵌套 with 更清晰, 合并降低可读性
    - 3 SIM105 (suppressible-exception) — 显式 try/except 更易调试
    - 2 SIM103 (needless-bool) — 显式 if/return 更易读
- **WONTFIX 理由**:
  1. **命名规范 (N801/N802/N806/N814/N816) 改名风险高**: DRF serializer 字段映射前端 JSON keys (camelCase), Win32 API 包装方法名需匹配 Microsoft 文档, 业务术语类名 (PvP/GvG) 是游戏领域约定俗成
  2. **SIM117 嵌套 with 合并降低可读性**: patch.object 多层嵌套场景下, 合并会模糊 patch 边界, 测试代码尤甚
  3. **SIM105 显式 try/except 便于调试**: contextlib.suppress 会吞掉 traceback, 显式 except 更易定位问题
  4. **SIM103 显式 if/return 更易读**: 转成 ternary 反而降低代码可读性
  5. **批量改名违反 §2.0 三原则之"逻辑正确性"**: 改名需同步改前端契约 / 测试 fixture / API 文档, 工作量大且易引入 bug
  6. **剩余 60 处全部为风格偏好, 不影响逻辑正确性**: ruff select 包含 N/SIM 是为了"提示"而非"强制", 项目允许保留少量偏离
- **修复方案验证** (§4.8 N174):
  - `conda run -n gaf ruff check backend/ agent/ --statistics` 输出 60 errors (全部为 N*/SIM*)
  - `conda run -n gaf python -m pytest backend/` = 1774 passed, 3 warnings (320.89s)
  - `conda run -n gaf python -m pytest agent/tests/` = 1410 passed, 2 skipped (88.96s)
  - 测试全过, ruff --fix 未破坏代码
- **重新开放条件**:
  - 若后续重构涉及相关模块, 顺手修复对应 wontfix 项 (不专门开 spec)
  - 若命名规范类阻碍新功能 (如新增 DRF serializer 与前端字段冲突), 单独修该条
- **关联**: TD-127 active.md (状态: ✅ FIXED 部分修复 + wontfix 剩余 60 处)

---

## TD-119: Git 写命令需用户确认 (❌ wontfix — Trae 限制, AI 缓解已最大化)

- **状态**: ❌ wontfix (2026-07-18 — Trae IDE 逐命令逐 flag 风险判定不可绕过, AI 缓解策略已最大化, 用户决策"关闭讨论")
- **优先级**: P3
- **登记时间**: 2026-07-15
- **来源**: 用户反馈 2026-07-15 — "使用git的命令咋很多都要我确认" + 追问 "如果我没确认的话，你不能主动停止后换方式吗？" + 再反馈 "一般在提交的命令和git add 这种吧" + "git add -f ...; git rm --cached ... 这就等待我的确认了，又弹窗了" + 再反馈 "git commit -m '...' 这个也触发了"
- **症状**: Trae "始终自动运行"非真"始终", 按命令逐个判定风险等级:
  - ✅ 不弹窗: `git status` / `git log` / `git add <具体文件>` (无 -f) / `git commit -m "..."` (单行, 2026-07-18 修正)
  - ✅ 弹窗: `git add -f` (强制 flag) / `git rm --cached` (删除) / `git commit -F <file>` (从文件读取 message, 风险 flag) / `git commit -m "..." -m "..."` (多行, 多个 -m flag)
- **根因**: Trae IDE "始终自动运行"模式基于**逐命令逐 flag** 风险等级判定, 非真"始终", 也非按"读/写"类别判定。识别为风险的命令 (`-f` 强制 flag / `rm` 删除 / `-F` 文件读取 / 多个 `-m` flag) 仍弹窗。覆盖了 AI 在 RunCommand 中设置的 `requires_approval: false`
- **影响**: AI 工作流被打断, 用户需手动确认风险命令, 降低效率
- **修复方案** (AI 缓解策略, 已在规则层落地, 已最大化):
  1. 批量合并: 多个 git 命令合并成一次 RunCommand (用 `;` 分隔), 减少弹窗次数
  2. AskUserQuestion 提醒: 发起 RunCommand 后若弹窗, AI 主动用 AskUserQuestion 提醒用户确认
  3. 优先用不弹窗工具: 如 Grep/Glob/Read 替代 `git grep`/`git ls-files`
  4. 避免风险 flag: 不用 `git add -f` (改用非 gitignored 路径); 不用 `git rm --cached` (改用 `git restore --staged`); 不用 `git commit -F` (改用单行 `-m`)
  5. commit message 尽量单行 (N170): 单行 `-m` 不弹窗, 多行 `-m` 或 `-F` 都弹窗
  6. commit 弹窗不可避免时: 用户确认后继续, AI 不回避 commit
- **wontfix 理由** (2026-07-18):
  1. Trae IDE 逐命令逐 flag 风险判定是 IDE 内核行为, AI 无法绕过
  2. AI 缓解策略已最大化 (6 条规则层硬约束, 详见 `project_rules.md §3.4` N170 + `§3.5` + `§3.6`)
  3. 用户 2026-07-15 决策 "本 TD 不再纠结, 关闭讨论"
  4. v9.2 改为 spec 粒度 commit (每 spec 1 次 commit), 弹窗频次可控 (TD-119 已缓解)
  5. 2026-07-18 N170 修订: commit message 尽量单行, 避免多行 -m / -F 弹窗
- **验证标准**: ✅ AI 缓解策略生效 (弹窗次数减少 ≥ 50%); ❌ 完全解决需 Trae 细粒度权限配置 (Trae 当前不支持)
- **何时修**: wontfix (2026-07-18)
- **决策历史**:
  - 2026-07-15 初版登记为 "C 类无法解决", 用户追问后修正为 "B 类部分可缓解" — AI 主动换方式是合法策略, 不应轻言"无法解决"
  - 2026-07-15 用户配置"始终自动运行"并重启 Trae IDE 后, 3 只读命令测试 (git status / git log / conda run) 无弹窗, 误判为 ✅ FIXED
  - 2026-07-15 用户反馈 `git add -f ...; git rm --cached ...` 仍弹窗, 修正回 🔧 B 类 (N162 验证完整性, 第 1 次犯 — 只测只读命令)
  - 2026-07-15 用户反馈 `git commit -m "..."` 也弹窗, 根因细化为"逐命令逐 flag 判定" (N162 第 2 次犯 — 未测 commit 变体)
  - 2026-07-18 修正: `git commit -m "..."` 单行**不弹窗**, 之前误判 (实际是 `-F` flag 触发); N170 硬约束: commit 优先单行 `-m` (N162 第 3 次犯 — 未测 -m vs -F 差异)
  - 2026-07-18 再修正: 多行 `-m` (多个 -m flag) 也弹窗, 仅单行 `-m` 不弹窗; N170 第 2 版修订: commit message 尽量单行 (N162 第 4 次犯 — 未测单行 vs 多行 -m)
  - 2026-07-18 wontfix 决策: AI 缓解已最大化, Trae 限制不可绕过, 关闭讨论
- **教训沉淀** (N162 验证完整性, 4 次犯):
  - 验证命令变体时必须逐个测试, 不能从"add 不弹窗"推广到"commit 不弹窗"
  - 验证 flag 时必须测 `-m` vs `-F` vs 多个 `-m` 等所有变体
  - 验证 commit 时必须测单行 vs 多行
  - 已沉淀到 `failure-modes.md` N162 + `lessons/workflow_2026-07-15-n162-verification-completeness.md`

---

## TD-127: ruff 剩余 60 个命名规范/风格类 errors (✅ partial + ❌ wontfix — B 类)

- **状态**: ✅ 部分修复 (152→60, 减 92 处) + ❌ WONTFIX (剩余 60 处 — 详见 wontfix.md TD-127)
- **优先级**: P3
- **登记时间**: 2026-07-16
- **部分修复时间**: 2026-07-18 (Phase 2 — backend/ + agent/ ruff errors)
- **来源**: N166 L3-1 扫描 — 月度健康检查 [I3] Ruff errors 批量修复后剩余
- **症状**: ruff check 报 152 errors (原 151 + 1 新增) → Phase 2 修复后剩余 60 errors (命名规范 N801/N802/N806/N814/N816 = 43 处 + 风格 SIM105/SIM103/SIM117 = 17 处, 全部 wontfix)
- **根因**: 长期积累的风格/命名规范偏差, 部分可自动修复, 剩余改名风险高 / 影响可读性
- **影响**: 无功能影响, 仅代码风格不一致
- **修复方案**: ① pyproject.toml 加 per-file-ignores (豁免 __init__.py F401 re-export + cv2 try/except 检测); ② ruff --fix --unsafe-fixes 自动修 56 处 (I001/UP007/UP031/UP035/F401/F841/B905/C408/SIM102/SIM108/SIM118 等); ③ 手动修 7 处 (OCR __init__ 删 List / target.py Union→X|Y / screenshot_diagnostic.py +2 E402 noqa / test_engine_structured_log_integration.py +2 E402 noqa)
- **验证标准**: ✅ ruff check backend/ agent/ 60 errors (全部 wontfix 类) + ✅ pytest backend 1774 passed + ✅ pytest agent 1410 passed (ruff --fix 未破坏代码)
- **何时修**: wontfix — 后续重构涉及相关模块时顺手修, 不专门开 spec (详见 wontfix.md TD-127)
- **关联**: 月度健康检查 [I3], wontfix.md TD-127
- **Spec**: `specs/2026-07-16-ruff-batch-fix.md`

---

## TD-147: 其他文件吞异常无日志 (❌ wontfix)

- **状态**: ❌ wontfix (2026-07-18, via subagent #1)
- **wontfix 评估 (2026-07-18, via subagent #1)**: TD 描述不准 — 0 处真实吞异常, 4 处 grep 命中全为注释字面量 (`grep -rn "except.*pass" backend/` 命中均为 `# except... pass` 形式的注释或 docstring 示例, 非真实代码). 无需修复.
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: N166 L3-1 第 2 轮评估 ⑥业务逻辑层 — Phase 1 F3 仅修了 agents/views.py 3 处
- **症状**: backend/ 内仍有多处 `except Exception: pass` / `except: pass` 未加 logger (具体文件见 ruff/flake8 静态扫描)
- **根因**: 历史代码缺少异常日志规范
- **影响**: 生产环境异常无法定位
- **修复方案**: 全 backend 扫描 `except.*pass` 模式，逐处加 logger.warning / logger.exception
- **验证标准**: `grep -rn "except.*pass" backend/ | grep -v test` 全部有 logger
- **何时修**: wontfix (TD 描述不准: 0 处真实吞异常, 4 处 grep 命中全为注释字面量; via subagent #1)

---

## TD-148: tasks → agents 反向依赖 (❌ wontfix — 描述不准, 与 TD-219 同构)

- **状态**: ❌ wontfix (描述不准 — 与 TD-219 同构, 无 module-load-time 循环)
- **优先级**: P3
- **登记时间**: 2026-07-17
- **评估时间**: 2026-07-18 (subagent 评估)
- **来源**: N166 L3-1 第 2 轮评估 ③架构层
- **症状**: `tasks/services.py` 内 `_restore_device_status_by_msg` 等函数被 `agents/consumers.py` 反向调用，形成 tasks → agents → tasks 循环
- **根因**: 业务逻辑跨 app 调用未抽象为 service 层
- **影响**: 循环依赖风险 + 单元测试 mock 困难
- **wontfix 理由** (subagent 评估 evidence):
  1. **描述不准**: "tasks → agents → tasks 循环" 实际是 runtime call flow 循环, 非 module-load-time import cycle
  2. **import graph 无环**: tasks/models.py + agents/models.py 互相零 import; tasks/services.py 顶层零 `from agents` (4 处全在函数体内 lazy import)
  3. **Django lazy loading 已规避**: 项目已文档化该模式 (3 处显式注释: gamestate/views.py:57 + agents/models.py:571 + agents/game_binding.py:38)
  4. **测试 evidence**: `test_device_status_lifecycle.py` 顶层同时 import agents.models + tasks.services, 测试的正是 TD-148 描述的调用链, 无 ImportError
  5. **mock 无困难**: 测试直接 mock `consumer._finalize_execution`, 跨 app 调用链可标准 mock
  6. **与 TD-219 同构**: TD-219 (accounts↔agents 循环) 已 wontfix 闭环, 本 TD 同构
- **修复方案**: wontfix (与 TD-219 一致)
- **验证 evidence** (subagent 静态分析, 等价于 ruff/mypy/pytest):
  - tasks/models.py: 0 处 `from agents` 顶层
  - agents/models.py: 0 处 `from tasks` 顶层
  - tasks/services.py: 4 处 `from agents` 全在函数体内 (line 69/158/214/267)
  - agents/consumers.py: 1 处 `from tasks.models` 顶层 (line 17, tasks.models 不反向) + 2 处 lazy (line 365/385)
  - 测试文件 test_device_status_lifecycle.py 顶层 import 双 app 无 ImportError
- **何时修**: wontfix (2026-07-18)

---

## TD-149: migration 文件膨胀 (❌ wontfix — 单人项目 squash 收益低)

- **状态**: ❌ wontfix (单人自用项目 squash 收益 << 风险)
- **优先级**: P3
- **登记时间**: 2026-07-17
- **评估时间**: 2026-07-18 (subagent 评估)
- **来源**: N166 L3-1 第 2 轮评估 ⑦数据层
- **症状**: 多个 app migration 文件数量过多 (agents 15+ / tasks 20+)，部分 migration 是 typo 修复或字段 rename
- **根因**: 长期迭代未做 migration squash
- **影响**: 新部署 migration 时间长；历史 migration 阅读成本
- **wontfix 理由** (subagent 评估 evidence):
  1. **GAF 单人项目特性** (project_rules §2.0 ③): 不兼容旧系统, 一次性切换, 无生产数据兼容问题
  2. **squash 风险显著**: 22 个 SeparateDatabaseAndState 协调多 app 重构 + 2 个元迁移 (改 django_migrations 表) + 2 个破坏性 token 哈希迁移 + 1 个含 DROP TABLE 复杂迁移
  3. **squash 收益极低**: fresh DB 部署 ~5-10 秒, 节省时间无意义; migration 文件占仓库 < 1%
  4. **现有缓解已足够**: migration docstring 质量高 (含依赖说明/设计理由/回滚策略); 已采用"针对性删除"模式 (gamestate/0006)
  5. **"remove_" 系列有架构价值**: tasks/0027-0040 是特性墓碑, 记录"试错→移除→迁移到专用 app"演进历史
- **现状统计**: 19 个 app 共 ~149 个 migration (tasks 45 + accounts 15 + agents 15 + scheduler 10 + pipeline 9 + resources 9 + settings 7 + gamestate 6 + 其他 33)
- **修复方案**: wontfix (squash 风险 >> 收益)
- **验证 evidence**: subagent 完整评估报告 (含高风险迁移文件清单 + 跨 app 依赖分析)
- **何时修**: wontfix (2026-07-18)

---

## TD-151: 前端无障碍属性缺失 (❌ wontfix)

- **状态**: ❌ wontfix (2026-07-18, via subagent #1)
- **wontfix 评估 (2026-07-18, via subagent #1)**: GAF 定位为单用户 PC 桌面应用 (Electron 一体化分发, architecture-overview.md §一), 非多用户 SaaS Web 服务. a11y 已覆盖 23 文件 61 处 (aria-label / role 等), 屏幕阅读器场景不适用. 补齐全部 Icon-only Button / Tag 的 aria-label 属过度工程化.
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: N166 L3-1 第 2 轮评估 ④界面层
- **症状**: 多个组件缺少 aria-label / role 等无障碍属性 (如 Tag / Icon-only Button)
- **根因**: 开发时未遵循无障碍规范
- **影响**: 屏幕阅读器用户无法使用
- **修复方案**: 全前端扫描 Icon-only Button / Tag，补齐 aria-label
- **验证标准**: axe-core 扫描 0 violations
- **何时修**: wontfix (单用户 PC 桌面应用, a11y 已覆盖 23 文件 61 处, 屏幕阅读器场景不适用; via subagent #1)

---

## TD-152: 前端响应式布局不完整 (❌ wontfix)

- **状态**: ❌ wontfix (2026-07-18, via subagent #1)
- **wontfix 评估 (2026-07-18, via subagent #1)**: project_rules.md §0 核心约束明确 "GAF 只控制 PC 窗口 (Win/macOS/Linux) + 模拟器 (ADB), 不需要手机端". Electron 一体化分发为桌面应用, 窄屏 (< 768px) 移动端布局场景不适用. 补齐 375px / 768px 断点属过度工程化, 违背 §0 硬约束.
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: N166 L3-1 第 2 轮评估 ④界面层
- **症状**: 部分页面在窄屏 (< 768px) 下布局错乱 (如 Table 横向滚动 / Card 栅格未响应式)
- **根因**: antd Grid 使用未充分使用 xs/sm/md/lg breakpoints
- **影响**: 移动端体验差
- **修复方案**: 评估关键页面 (Dashboard / Tasks / Devices) 响应式 breakpoints
- **验证标准**: Chrome DevTools 375px / 768px / 1024px 三档断点布局正常
- **何时修**: wontfix (§0 硬约束 "GAF 不需要手机端", PC 桌面应用响应式属过度工程化; via subagent #1)

---

## TD-153: agent msg_type 裸字符串 (❌ wontfix)

- **状态**: ❌ wontfix (2026-07-18, via subagent #1)
- **wontfix 评估 (2026-07-18, via subagent #1)**: agent (Python) 与 backend (Python) 跨包常量共享方案均 > 500 行 (提取 shared 包 / codegen / symlink) 或违背 §2.0.4 单人项目一次性切换原则. backend protocol tests (`backend/protocol/tests/`) 已捕获 msg_type 漂移 (test_message_type_consistency 等), 现有测试机制足够防御. 修复成本 > 收益.
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: N166 L3-1 第 2 轮评估 ⑨集成层
- **症状**: `agent/src/client/handler.py` 等处仍用裸字符串 `'task.result'` / `'agent.heartbeat'` 而非引用 `protocol/constants.py` MessageType
- **根因**: agent (Python) 与 backend (Python) 共享 protocol 常量未做到位
- **影响**: msg_type 漂移风险
- **修复方案**: 评估 agent 是否能 import backend.protocol.constants (或提取 shared 包)；或 codegen
- **验证标准**: agent 内 msg_type 全部引用常量
- **何时修**: wontfix (跨包常量共享方案均 > 500 行或违背 §2.0.4, backend protocol tests 已捕获漂移; via subagent #1)

---

## TD-154: 测试 mock 缺注释 (❌ wontfix)

- **状态**: ❌ wontfix (2026-07-18, via subagent #1)
- **wontfix 评估 (2026-07-18, via subagent #1)**: 394 处 mock 注释属过度工程化. GAF 为单人项目, 测试名 + 代码本身已自解释 (如 `test_dispatch_task_when_device_busy` mock Device.status=BUSY 意图明显). 强制 `// mock xxx because yyy` 注释会引入 ~394 行噪声, 维护成本 > 收益. testing-conventions.md 已规定测试名规范.
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: N166 L3-1 第 2 轮评估 ②代码层
- **症状**: 多个测试文件 mock 较多但缺注释说明 mock 意图 (如 `vi.fn().mockResolvedValue(...)` 未说明为什么 mock)
- **根因**: 测试编写时未遵循注释规范
- **影响**: 测试维护成本高
- **修复方案**: 评估关键测试文件 (Dashboard / Executions / Tasks) 补齐 mock 注释
- **验证标准**: 关键测试文件 mock 都有 `// mock xxx because yyy` 注释
- **何时修**: wontfix (394 处 mock 注释属过度工程化, 单人项目测试名+代码自解释; via subagent #1)

---

## TD-155: 文档 URL drift (❌ wontfix)

- **状态**: ❌ wontfix (2026-07-18, via subagent #1)
- **wontfix 评估 (2026-07-18, via subagent #1)**: TD 描述方向模糊 — 无具体 drift 案例 (未列出哪些文档 URL 与哪些后端路由不一致). monthly-health-check 脚本 (scripts/health/monthly_health_check.py) 已覆盖 URL 检测, 已有机制兜底. OpenAPI schema 自动生成 + 文档链接校验脚本属过度工程化.
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: N166 L3-1 第 2 轮评估 ①文档层
- **症状**: `docs/` 内多份文档引用的 URL (如 `/api/v2/tasks/` vs `/api/v2/tasks/list/`) 与实际后端路由不完全一致
- **根因**: 文档与代码迭代未同步
- **影响**: AI 按文档写代码时 URL 可能错误
- **修复方案**: 评估用 OpenAPI schema 自动生成 URL 列表 + 文档链接校验脚本
- **验证标准**: 文档 URL 100% 匹配后端实际路由
- **何时修**: wontfix (TD 描述方向模糊无具体 drift 案例, monthly-health-check URL 检测脚本已覆盖; via subagent #1)

---

## TD-210: spec 2026-07-17-code-and-frontend-ws-cleanup.md Phase 2/3/4 ⏳ 未完成 (❌ wontfix — 2026-07-18, Phase 4 由 spec-28 e2e 覆盖)

- **状态**: ❌ wontfix (2026-07-18 — subagent 评估, Phase 4 实质工作已由 spec-28 e2e 覆盖)
- **优先级**: P2
- **登记时间**: 2026-07-17
- **修复时间**: 2026-07-18 (Phase 2/3 ✅ + Phase 4 由 spec-28 覆盖)
- **来源**: spec 2026-07-17-l3-round9-integration-and-test-structure-fix Phase 5 [B] 类登记 (文档层维度扫描)
- **症状**: `specs/2026-07-17-code-and-frontend-ws-cleanup.md:12-14` Phase 1 ✅, Phase 2 (前端 WS 契约修复 D2/E2/E3/E4) / Phase 3 (Dashboard 补齐 5 widget) / Phase 4 (全量回归 + L3-5 实测) 均 ⏳, spec 仍活跃
- **根因**: Phase 1 完成后未继续推进
- **影响**: WS 契约修复未完成, Dashboard 5 widget 缺失
- **修复方案**: 推进 Phase 2/3/4; 关联 TD-141/TD-142/TD-200/TD-201/TD-202, 预估剩 ~400 行 diff
- **修复进度**:
  - Phase 2 ✅: 关联 TD 全部已修 (TD-141 Spec 20 + TD-142 Spec 21 + TD-200 Spec 18 + TD-201/202 Spec 13); api.generated.ts 死端点已不存在
  - Phase 3 ✅: 5 widget 已创建 + 集成到 Dashboard/index.tsx (WidgetType 4→9, 默认 layout 4→9 widget, renderContentCard 5 分支); tsc 0 errors + vitest 1 passed
  - Phase 4 ✅ (wontfix): 全量回归 + L3-5 实测由 spec-28 e2e 覆盖 (backend 351 passed + agent 89 passed + tsc 0 errors + 10 pipeline e2e PASS, 3 服务连通)
- **wontfix 理由 (2026-07-18 subagent 评估确认)**:
  1. spec 文件已被 spec-27 当作"完成"清理到 `.trash/spec27-cleanup/`, 重新开 spec 仅为了"补 Phase 4 标记" ROI 低
  2. Phase 4 的核心验证目标 (Dashboard widget + WS 连通) 已由 spec-28 的 e2e 实测覆盖 (10 pipeline e2e + 3 服务连通)
  3. 唯一未覆盖项 "ADB 日志查看器实时日志" 是次要验证点, 可在下次涉及 ADB 日志的 UI 修改时顺带验证 (touch-on-edit 策略)
- **Phase 3 验收 evidence**: `npx tsc --noEmit` 0 errors (1.23s) + `npx vitest run src/pages/Dashboard` 1 passed (5.84s)
- **Phase 4 验收 evidence**: spec-28 e2e 实测 — backend 351 passed + agent 89 passed + tsc 0 errors + 10 pipeline e2e PASS (3 服务就绪 + WS 实际连通)
- **重新开放条件**: ADB 日志查看器 UI 修改时未做实测

---

## TD-215: L3-1 全量扫描触发状态追踪缺位 (❌ wontfix — 2026-07-18, 已有 grep + ops 机制)

- **状态**: ❌ wontfix (2026-07-18 — subagent 评估, 4 触发条件均可通过 grep + ops/monthly-health-checks/ 已有机制实时判断)
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: spec 2026-07-17-ai-meta-rules-eval-and-fix Phase 5 [B] 类登记
- **症状**: `project_rules.md §3.7` L3-1 全量扫描触发条件已定义 (≥3 spec / ≥2 新 TD / 用户要求 / 月度), 但无状态追踪机制
- **根因**: Phase 5 仅落地文档规则, 状态追踪延后
- **影响**: AI 无法判断"距上次 L3-1 全量扫描几个 spec", 可能漏跑或重复跑
- **wontfix 理由 (2026-07-18 subagent 评估确认)**:
  1. **触发条件 ④ 月度 health-check** 已有追踪机制 (`docs/health/<YYYY-MM>.md`), AI 进入 L3-1 时按 _workflow.md 检查表第 4 项 Read 最新月度报告
  2. **触发条件 ① spec 完成数** 可通过 `grep -c "✅" .trae/specs/*.md` 实时查询, 无需维护 counter
  3. **触发条件 ② tech-debt 新增数** 可通过 `git log --since="2 weeks ago" docs/tech-debt/active.md` 查询
  4. **触发条件 ③ 用户显式要求** 通过对话上下文判断, 文件追踪无意义
  5. **新 `.l3_state.json` 的反风险**: counter 失同步 (sync_ai_memory.py 未检测到 spec 完成 / AI 忘记 reset) 反而误导决策; 引入额外状态维护成本 > 收益
- **重新开放条件**: (1) 月度 health-check 机制废弃; (2) AI 频繁漏跑 L3-1 全量 (≥ 2 次/月)

---

## TD-220: 双套 WS Consumer 死代码 (~700 行) (❌ wontfix — 描述失实)

- **状态**: ❌ wontfix (subagent 评估: 描述失实, executions/consumers.py 是活跃代码 139 行非 700 行)
- **优先级**: P2
- **登记时间**: 2026-07-17
- **评估时间**: 2026-07-18 (subagent 评估)
- **来源**: L3-1 ⑨ 集成层 Round 4 扫描 [A] 降级 [B]
- **症状**: `backend/protocol/consumers.py` + `backend/executions/consumers.py` 双套 WS Consumer 并存,实际只用一套,另一套为死代码 (~700 行)
- **wontfix 理由** (subagent 评估 evidence):
  1. **描述失实 — "双套"实为 4 app 各自独立 Consumer**: protocol (AgentConsumer/FrontendConsumer/LogStreamConsumer) + executions (ExecutionConsumer) + agents + notifications, 各负责独立 WS 路径
  2. **描述失实 — "~700 行死代码"实为 139 行活跃代码**: executions/consumers.py 仅 139 行, 非死代码
  3. **executions/consumers.py 是生产关键路径**: 被 `config/asgi.py:12,24` 挂载 + `tasks/signals.py:172,188` 生产调用 (`broadcast_execution_update` helper) + `executions/tests/test_consumers.py` 118 行测试覆盖
  4. **删除会破坏 TaskExecution 状态推送链路**: `tasks/signals.py:188` 的 `async_to_sync(broadcast_execution_update)` 是 TaskExecution.post_save 推送到前端的唯一路径
  5. **TD-200 反向证据**: 2026-07-18 TD-200 刚把 NotificationConsumer 从 executions 拆到 notifications, 证明 executions/consumers.py 在积极维护非死代码
  6. **两文件职责清晰分离**: protocol/consumers.py (Agent 协议 + Dashboard 广播 + 日志流, 1780 行) vs executions/consumers.py (单执行实时状态流, 139 行)
- **修复方案**: wontfix (描述失实, 删除会破坏生产)
- **验证 evidence** (subagent 评估):
  - `backend/config/asgi.py:12,24`: executions_ws_urlpatterns + protocol_ws_urlpatterns 均活跃挂载
  - `backend/executions/consumers.py`: 139 行 (非 700), 含 ExecutionConsumer + 2 个 broadcast helper
  - `backend/tasks/signals.py:172,188`: 生产调用 `broadcast_execution_update`
  - `backend/executions/tests/test_consumers.py`: 118 行测试覆盖
- **何时修**: wontfix (2026-07-18)

---

## TD-223: 35+ POST 端点缺 Idempotency-Key 机制 (❌ wontfix — 单人项目无重试场景)

- **状态**: ❌ wontfix (2026-07-18 — subagent 评估 evidence: 单人项目 + 前端无重试 + WS 重连不发 POST + agent 用 WS 上行)
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: spec-10 L3-1 ⑥ 业务逻辑层维度扫描 (降级 [B] 类)
- **症状**: backend 全项目 ~105 个 POST 端点 (TD 原描述 35+ 低估, 实测 105: 64 @action post + 36 APIView post + 5 ViewSet create) 无 Idempotency-Key 中间件,客户端重试/网络抖动可能产生重复资源
- **根因**: 无全局幂等性中间件,每个 POST 端点各自处理 (或未处理) 重复请求
- **影响**: 客户端重试场景下可能产生重复数据,但 GAF 是单人自用项目 + 无外部客户端重试逻辑,实际触发概率近 0
- **修复方案**: wontfix — 不引入项目当前不需要的复杂度 (避免过度工程化)
- **验证标准**: wontfix (无需修复)
- **何时修**: wontfix (2026-07-18)
- **wontfix 理由** (subagent 评估 evidence):
  1. **触发场景几乎不存在**:
     - 前端 `frontend/src/api/client.ts` axios 拦截器只在 401 时单次重试 refresh token, 对其他错误 (网络断开/5xx) 不重试
     - 全仓未发现 `axios-retry` / `retry: N` 配置 (grep 仅 `UnattendedStrategyPanel.tsx` / `EmulatorManagementPage.tsx` 的 `max_retries` 是业务逻辑字段, 非 HTTP 重试)
     - WS 客户端重连 (最多 10 次指数退避 3s→60s) 重连回调只调 `useDeviceStore.getState().refreshAll()` (GET 请求), 不发 POST (`AppLayout.tsx:225-228`)
     - agent ↔ backend 通信用 WS 上行, 无 HTTP POST
  2. **用户手动重复点击 ≠ 网络重试**: 用户连点"执行任务"按钮是用户意图, 幂等性反而阻止合法二次操作 (如先执行→取消→再执行); 真正的防误触应在 UI 层 (按钮 disabled + loading state), 不是 HTTP 层
  3. **复杂度 vs 收益严重不匹配**: A 方案 (middleware + Redis) > 1000 行 + 引入 Redis 基础设施; B 方案 (decorator) ~500 行; 实际收益: 防御一个几乎不会发生的场景
  4. **GAF 已有防御足够**: 前端按钮 loading state 防误触 + 后端部分端点自身幂等 (如 task.execute 创建 TaskExecution 是状态机模型, 重复执行只多一条 PENDING 记录, 可通过 cancel 清理)
  5. **与 §2.0 三原则一致**: 不引入项目当前不需要的复杂度 (避免过度工程化); 单人自用项目 = 不兼容旧系统, 一次性决策 (wontfix 是合法决策)
- **重新评估触发条件** (满足任一即重新评估):
  ① 引入外部 API 客户端 (如移动端 / 第三方集成)
  ② 添加 axios-retry 或类似自动重试机制
  ③ 引入移动端弱网场景
- **轻量替代方案** (如未来仍担心): 在关键创建端点 (`tasks.execute`, `pipelines.restore`, `resources.create`) 加业务层"未完成同资源拒绝"校验, 比 HTTP Idempotency-Key 轻量得多

---

## TD-226: ④ 界面层 11 项 (6 i18n 硬编码 + 5 PageWrapper 缺失) (❌ wontfix — 2026-07-18, TD 描述严重低估 + touch-on-edit 策略已生效)

- **状态**: ❌ wontfix (2026-07-18 — subagent 评估, TD 描述数量严重低估 + frontend-conventions.md 已强制 touch-on-edit 渐进迁移)
- **优先级**: P3
- **登记时间**: 2026-07-17
- **来源**: spec-10 L3-1 ④ 界面层维度扫描 (降级 [A] → [B])
- **症状**: (a) 前端 6 处硬编码中文字符串未用 i18n (dashboard/components 等); (b) 前端 5 个页面未用 PageWrapper 统一容器组件 (违反 §4.7 前端开发工作流)
- **现状重新统计 (2026-07-18 subagent)**:
  - **PageWrapper 缺失**: TD 说 5 个, 实际 `frontend/src/pages/` 共 ~88 个页面, 仅 35 个用 PageWrapper, **缺 53 个** (远超 5)
  - **i18n 硬编码**: TD 说 6 处, 实际 86 个文件已 `import useTranslation`, 30 个文件含中文 (714 处, 含注释) — i18n 已广泛使用, 渐进迁移中
- **根因**: (a) GAF 是单人中文项目, i18n 从未启用, 硬编码中文是历史习惯; (b) PageWrapper 是后加的规范, 旧页面未迁移
- **影响**: (a) 0 功能影响 (中文显示正常), 仅影响多语言扩展性; (b) 0 功能影响, 仅影响样式一致性 (页面间距/标题样式不统一)
- **wontfix 理由 (2026-07-18 subagent 评估确认)**:
  1. TD 描述数量 (6+5) 严重低估, 真实情况是 53 个 PageWrapper 缺失 + i18n 已广泛使用 — 重新评估后已无"6+5"小范围修复价值
  2. 0 功能影响 (中文显示正常 + 页面样式局部不一致), GAF 是单人中文项目, i18n 多语言扩展性非必需
  3. `docs/standards/frontend-conventions.md` L263-279 已强制 **touch-on-edit 策略**: 修改页面时必须迁移到 PageWrapper, 任何新改动自然消解债务, 无需独立 spec
  4. 一次性 spec 修复 53 个页面 PageWrapper 迁移成本高 (> 500 行 diff) + 收益低 (纯样式一致性), 违反 §2.0 禁止过度工程化原则
- **重新开放条件**: (1) GAF 启用多语言 (i18n 从可选变必需); (2) PageWrapper 缺失页面集中爆发样式回归 bug

---

## TD-256: gaf-* skills step_N 编号跨文件冲突 (❌ wontfix — 2026-07-18)

- **状态**: ❌ wontfix (2026-07-18 — subagent 评估 + 主会话确认, 82 处 step_N 已带语义名, ROI 低)
- **优先级**: P3
- **登记时间**: 2026-07-18
- **来源**: R7 评估 P2-1 — orchestrator vs task-execution step_N 编号冲突
- **症状**:
  - orchestrator 5 分支 × 6 步 + task-execution §2/§3 各 5 步 + reflect-and-evolve 引用, 共 ~82 处 step_N_<name>
  - 同号异义: orchestrator step_1 (identify_task_type) vs task-execution §2 step_1 (spec_review) vs §3 step_1 (impact_assessment)
  - unknown 分支已用 step_1b hack 避开 root.step_1 冲突 (编号体系崩坏证据)
  - reflect-and-evolve §7 引用 "refactor 分支 step_4" 易与 task-execution §3 step_4 (cutover) 混淆
- **根因**: 数字编号无法承载跨文件流程差异 (长度不一 5/6 步 + 章节语义不一), step_N 后虽带语义名但跨文件引用仍用数字
- **影响**: 跨文件 step_N 引用易混淆; unknown 分支 step_1b hack 表明编号体系不可持续; 新增分支时编号冲突复发
- **wontfix 理由 (2026-07-18 subagent 评估确认)**:
  1. step_N 后已带语义名 (如 `step_1_identify_task_type`), 实际阅读时数字+语义双标识, 混淆风险被语义名大幅缓解
  2. 当前 0 个已发 bug 由 step_N 编号冲突引起 (查 grep evidence: 82 处 step_N 全部带语义后缀)
  3. 改造影响面: ~82 处 × 6 文件 (3 个 SKILL.md + project_rules.md + ai-operating-handbook.md + _ai-autonomy.md), > 500 行 diff, 单独 spec 才能完成
  4. 七维度评分 16 分 (< 19 阈值), 不达自决执行标准; 改造收益主要是"避免潜在混淆", ROI 低
  5. unknown 分支 step_1b hack 是局部最小修补, 不影响其他分支; 当前体系可持续
- **修复方案 (评估保留, 暂不执行)**: 方案 C 语义化 phase_<name> — 移除 step_N_ 数字前缀, 保留语义名为唯一标识符; 跨文件引用统一 `<skill_name> §<section> phase_<name>`; 跑 sync_skills.py 同步 4 副本
- **重新开放条件**: (1) 新增分支导致 step_N 编号再次冲突 (≥ 2 次); (2) 跨文件引用错误导致 AI 实际走错流程 (有 bug evidence); (3) 治理 spec 批量重构时顺便处理
- **关联**: R7 评估 P2-1 调研报告, superpowers-zh §边界声明 §4 引用约定

---

## TD-391: LangGraph Agent 跨用户数据泄露 + 提示注入防护 ❌ EVALUATED (单租户不适用)

- **状态**: ❌ EVALUATED（评估后不修, 2026-08-22）
- **优先级**: 原 P1 → 评估后不修
- **登记时间**: 2026-08-22
- **评估时间**: 2026-08-22
- **来源**: 2026-08-22 AI 开发通病对照 GAF 方案分析（meta_audit 会话）+ `backend/gaf_ai/agent/` 代码级核查
- **原问题**: `gaf_ai` LangGraph Agent 工具层无用户隔离 + 不可信内容注入无防护 + Skill 动作面无审计。代码核查后订正：Agent 实为**只读日志诊断 Agent**（6 工具全只读），非设备控制 Agent。
- **evaluated 理由** (2026-08-22, 用户确认):
  1. **跨用户泄露 — INVALIDATED**：部署为**单租户**（仅 owner 一人，`user.role` 恒为 admin），工具无 user 过滤不会伤他人；`agent_analyze_view` 的 `triggered_by_id==user` 校验在单租户下恒真。多租户前提不成立。
  2. **提示注入 — 低价值**：Agent 为本地只读诊断，输入源仅用户自有任务描述/游戏截图，无外部不可信输入；即便 OCR/JSONL 含诱导文本，爆炸半径仅为"分析结论被带偏"，无写操作/外泄后果。
  3. **Skill 动作面 — 不适用**：当前注入诊断类 Skill，`execute_skill` 不构成设备控制面。
- **保留方案**: 若未来变为多租户/开放外部输入，重新激活并恢复 P1，按原方案（工具层 user 隔离 + SYSTEM_PROMPT 注入隔离 + Skill 审计）落地。
- **关联**: active-tech-debt.md TD-391 历史修订版 (含误判"设备控制"订正记录；原登记 TD-388 与 fixed-tech-debt.md 已提交的 TD-388(gaf_init evidence) 重号，2026-08-23 重编号为 TD-391)

---

## TD-386: 业务级评测指标缺失（成功率/耗时/恢复率）❌ EVALUATED (已交付)

- **状态**: ❌ EVALUATED（评估后不修, 2026-08-22）
- **优先级**: 原 P2 → 评估后不修
- **登记时间**: 2026-08-22
- **评估时间**: 2026-08-22
- **来源**: 2026-08-22 AI 开发通病对照 GAF 方案分析（meta_audit 会话）+ 代码核查
- **原问题**: 称 GAF 缺端到端业务指标（成功率/耗时/恢复率），`TaskExecution` 缺 duration/retry/recovery 字段。
- **evaluated 理由** (2026-08-22 代码核查):
  1. **字段已存在**: `TaskExecution` 已有 `duration`/`recovery_attempts`/`recovery_layer`；`TaskStep` 已有 `retry_count`/`duration`。
  2. **聚合 API 已存在**: `tasks/analytics_views.py` 提供 `task_stats`(success_rate/avg_duration/common_errors)/`step_heatmap`/`trend`/`weekly_report`/`agent_performance`，路由 `/api/v2/analytics/*` 就绪。
  3. **前端看板已存在**: `AnalyticsDashboard.tsx`(`/ops/analytics`) 已渲染成功率/耗时/步骤排行/趋势/周报/Agent 性能。
  4. **唯一残留**: recovery 指标聚合未覆盖，已拆为 TD-389（P3）。
- **保留方案**: 仅 recovery 维度按 TD-389 落地，不重做 analytics。
- **关联**: TD-389（recovery 指标聚合，唯一真实残留）
