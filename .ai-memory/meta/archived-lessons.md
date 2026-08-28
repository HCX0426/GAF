---
maintainer: derived-manual
source: .ai-memory/meta/archived-lessons.md
load_when: [查老 N## 教训, 历史回顾, N## 编号连续性检查]
priority: low
symptom: [workflow:archived-lesson, lesson:historical]
solution: 按需 grep 加载对应 lessons/<n##>.md 文件, 不主动加载
related_files:
  - .ai-memory/meta/failure-modes.md
  - .ai-memory/lessons/
  - .trae/rules/project_rules.md
created_by: AI
generated: 2026-07-07
auto_updated: 2026-07-18
last_manual_edit: 2026-07-20
---

# Archived Lessons — N## 归档索引（v9.0 分活跃/dormant/归档）

> **v9.0 重构**（gaf-workflow-v9-slim 闭环 + Task A.2 编号机制 — 2026-07-07，v9.1 归一化 2026-07-14）:
> - 本文件列出**已归档**的 N## 教训（已闭环或近 30 天无触发）
> - 详细内容仍在 `.ai-memory/lessons/` 里, 按需 grep 加载
> - 活跃 N## 索引在 `.ai-memory/meta/failure-modes.md`（v9.1 从 project_rules.md §6.4 归一化到此; TD-174/199 修复 2026-07-18 计数同步; 计数为动态统计, 勿在此硬编码 — B1 教训 2026-08-22）
> - **dormant N## 索引**（家族合并子条目，见下方 § Dormant N## 索引）
> - 完整索引（含归档）在 `failure-modes.md`（Active + Retired + Dormant 条数以 failure-modes.md 各段实际行数为准, 动态变化; 本文件另存 1 条归档 + 14 条 Dormant Marker (P2 自动归档) + 5 条 Dormant 历史 (仅在 archived-lessons.md, 不在 failure-modes.md §Dormant) + 6 条早期无编号）
> - **何时解档**: 同根因复发 → 移回 `failure-modes.md` 活跃表

## 状态四档判定标准 (v9.0 Task A.2; v9.1+ 加退役档 — 2026-07-18 spec-18 Phase 3 补丁)

| 状态 | 判定标准 | 位置 | 索引行为 |
|------|---------|------|---------|
| **活跃** | 近 30 天有触发 OR 核心 AI 行为硬约束 | `failure-modes.md` Active 段 (v9.1 归一化) | 独立索引，AI 主动加载 |
| **dormant** | 同根因家族合并后的子条目（保留在主条目"家族成员复发时间线"段，不独立索引） | 本文件 § Dormant N## 索引 | 不独立索引，AI 通过主条目加载 |
| **归档(deprecated)** | dormant 超过 6 个月 + 无新复发 + 无 Y/N 矩阵引用 | 本文件 § 归档 N## 索引表 | 仅按需 grep 加载 |
| **退役(retired)** | N## 编号永不复用, 但硬约束已沉淀到 rules/skills, 不再独立索引 (M0.M 闭环) | `failure-modes.md` §Retired N## 索引 | 不独立索引, Y/N 矩阵保留在家族主条目 |

## Dormant N## 索引（v9.0 家族合并 — 2026-07-07）

> 以下 N## 已合并到家族主条目，**不独立索引**，但仍保留 N## 编号（编号永不复用）。
> 详细复发历史在主条目"家族成员复发时间线"段。
> **spec-24 A-12 (2026-07-18)**: 与 `failure-modes.md §Dormant` 重复的 8 条 (N107/N110/N114/N113/N115/N127/N128/N130) 已删除, 权威源在 failure-modes.md §Dormant; 本段保留 6 条独有条目 (M2.D/N14/N101/N135-ws/N134-recurrence/N119) — N119 (TD-182 修复 2026-07-18) 因 lesson 文件保留在 lessons/ root 作历史参考, 在本段记录文件位置。

| N## | 家族主条目 | 合并原因 | 原独立文件路径 (历史参考 — 文件已删除, TD-183 修复 2026-07-18) |
|:---:|-----------|---------|---------------------|
| M2.D | N105 (commit 透传) | 同根因家族延伸 — pre-commit stages | `2026-06-17-m2d-pre-commit-stages.md` (已删除) |
| N14  | N126 (诚实标记) | 同根因家族早期 — 假实现审计 | (早期 lesson，无独立文件) |
| N101 | N126 (诚实标记) | 同根因家族早期 | (早期 lesson，无独立文件) |
| N135-ws | N135 (浏览器验证) | 同根因家族延伸 — WS Provider mount | `2026-07-05-n135-ws-provider-must-be-mounted.md` (已删除) |
| N134-recurrence | N134 (工作流触发) | 同根因家族复发 — reflection skipped | `2026-07-05-n134-recurrence-reflection-before-commit.md` (已删除) |
| N119 | N111 (命令超时) | 同根因家族 — 命令挂起早期变体 | `N119-m2b-command-hang.md` (保留在 lessons/ root 作历史参考, TD-182 修复 2026-07-18) |

**dormant → 归档(deprecated) 转换条件**:
- dormant 状态持续超过 6 个月
- 期间无新复发（主条目未追加新时间线）
- 无 Y/N 矩阵引用（`yn-matrices.md` 不再提及）
- 满足以上 3 条 → 移到 § 归档 N## 索引表

## 归档判定标准（已闭环 OR 罕见触发）

| 条件 | 示例 |
|------|------|
| 已闭环（v8.x / M1.x / R34 等明确标记） | N95 v8.6 闭环 / N116 M1.G 闭环 |
| 近 30 天无触发（罕见场景） | N131 仅浏览器测试时 / N138 仅 agent COM 工作时 |
| 治理元教训（无独立 Y/N 矩阵） | N132 文档职责分离 |

## 归档 N## 索引表

> **spec-13 Phase 5 [A]-R5-1 修复 (2026-07-17)**: 移除 15 个双重漂移 N## (N95/N116/N117/N118/N122/N124/N131/N132/N133/N136/N137/N138/N139/N141/N145) — 这些 N## 索引保留在 `failure-modes.md` Active 段, 不在归档段重复。仅保留真归档条目 N30。

| N## | 主题 | 归档原因 | Lesson 链接 |
|:---:|------|---------|-------------|
| N30 | SKILL.md 与 project_rules.md 章节漂移 | v8.5 时代早期教训, 已被 N95 v9.0 真二分制 + N132 文档治理覆盖 | `lessons/N30-skill-rules-drift.md` |
| N164 | L1/L2 不加载教训内容 → AI 重复犯错 | trigger_count=1, TD-343 归档 | `lessons/archived-early/N164-l1-l2-no-content-load-repeated-mistakes.md` |
| N168 | backup/restore 双套反模式 + SQL 注入 | trigger_count=1, TD-343 归档 | `lessons/archived-early/N168-backup-restore-security-fix.md` |

## 解档流程

当某归档 N## 同根因复发时:

1. AI 在反思中发现归档 N## 重新触发
2. 移动对应行从本文件 → `failure-modes.md` 活跃表 (v9.1 归一化: §6.4 已迁到 failure-modes.md)
3. 在本文件对应行标记 "🔄 已解档 <date>, 移回活跃表"
4. 跑 `git add .ai-memory/meta/archived-lessons.md .ai-memory/meta/failure-modes.md && git commit -m "refactor(rules): re-activate N## from archive (recurrence)"`

## 早期无编号 lessons 索引 (v9.0 Task B.1 — 2026-07-07)

> 以下 6 个早期 lessons 在 N## 编号机制建立前创建，未分配 N## 编号。
> 保留在 `lessons/archived-early/` 子目录作为历史归档，**不参与** sync_ai_memory 索引。
> 同根因复发时，应作为新 N## 教训登记（不复活早期文件）。

| 文件 | 主题 | 一句话摘要 |
|------|------|-----------|
| `archived-early/2026-06-10-agent-popup-bug.md` | agent-protocol | Django runserver autoreload 导致 Agent 父子进程重复启动 + 弹窗 |
| `archived-early/2026-06-14-api-404-tasks.md` | api-design | POST /api/v2/tasks 返回 404（缺尾随斜杠 + DRF ViewSet 路由） |
| `archived-early/2026-06-14-capability-mismatch.md` | agent-protocol | Agent 能力声明与 Backend 期望不匹配（握手时缺双向能力声明） |
| `archived-early/2026-06-14-message-frame-format.md` | agent-protocol | WebSocket 消息帧解析失败（4 字节长度前缀 + JSON body 未统一） |
| `archived-early/2026-06-14-pipeline-stuck-running.md` | pipeline | Pipeline 节点永远停留在 running 状态（缺超时 + 心跳检测） |
| `archived-early/2026-06-14-spec-overengineering.md` | spec | Spec 自身膨胀失控（v9 限行 + 零和博弈：删 1 加 1） |

**复发处理流程**:
1. 同根因问题复发 → 创建新 N## lesson（如 N150+）
2. 在新 lesson 的 `related_files` 段引用对应早期文件作为历史背景
3. 不复活早期文件（保持 archived-early/ 只读）

## Dormant Marker N## 索引 (P2 自动归档 — 治本机制 2026-07-16)

> **spec-23 Phase 3 A-11 (2026-07-18)**: 移除 5 条双重索引 (N147/N153/N155/N162/N163) — 这些家族合并子条目已在 `failure-modes.md` §Dormant N## 索引中, 不在本段重复。本段仅保留 M0.A/M0.M 闭环的 dormant markers (无 Y/N 矩阵引用, 无家族主条目)。

| N## | 原索引行 | 归档原因 |
|:---:|---------|---------|
| N1 | \| N1 \| YAML 解析失败 \| front matter 缩进/引号错 → `python -c "import yaml; ..."` 验证 \| (M0.A 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N2 | \| N2 \| IO 错误 \| 磁盘满/权限拒绝/文件被占用 → 看错误路径 → 释放文件 \| (M0.A 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N3 | \| N3 \| 同步超时 \| sync > 30s → `--dry-run --root <path>` 隔离慢仓库 \| (M0.A 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N4 | \| N4 \| session 过期 \| 24h TTL 到期 → `check_session_active.py --destroy` + `--create` \| (M0.A 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N5 | \| N5 \| evidence 缺失 \| 3 步模板未填 → `mkdir -p .ai-memory/evidence/<date>-<task>/` + 复制模板 \| (M0.A 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N6 | \| N6 \| lessons 缺字段 \| front matter 缺必填 → 补 `symptom/solution/related_files/created_by` \| (M0.A 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N7 | \| N7 \| spec 不一致 \| spec/tasks/checklist 互相矛盾 → `check_spec_consistency.py --fix` \| (M0.A 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N8 | \| N8 \| 决策树不一致 \| 4 副本漂移 → `sync_skills.py --check` + 强制同步 \| (M0.A 闭环, v9.0 单一权威源已消除) \| | dormant marker (已合并/闭环/dormant) |
| N92 | \| N92 \| PowerShell CJK 乱码 \| stdout cp936 → `import _encoding_safe` + `PYTHONIOENCODING=utf-8` \| (M0 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N93 | \| N93 \| AI 甩命令给用户 \| 反模式 — 必须 0 容忍, AI 自跑命令不甩用户 \| (M0 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N94 | \| N94 \| SKILL.md 决策树副本放错根 \| Trae IDE 识别不到 → 检查 `.trae/skills/` 路径 \| (M0 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N99 | \| N99 \| Vite 缓存旧代码 \| `rm -rf node_modules/.vite` 后重启 dev server \| (M0.M 闭环) \| | no lesson file + refcount=0 |
| N103 | \| N103 \| 旧 skills/ YAML 重复 \| 旧 `GAF/skills/*.yaml` 已删, 用 `.ai-memory/lessons/` + `.trae/skills/` \| (v8.4 闭环) \| | dormant marker (已合并/闭环/dormant) |
| N104 | \| N104 \| AI 不知 docs/ 有什么 \| 跑 `sync_docs_index.py` 看 `meta/docs-index.md` \| (v8.4 闭环) \| | dormant marker (已合并/闭环/dormant) |

## Y/N 矩阵归档 (从 yn-matrices/_workflow.md 迁入 — 2026-07-18)

> 以下 Y/N 矩阵因触发条件极窄或索引已归档，从 `yn-matrices/_workflow.md` 迁入本文件作历史参考。

### ⑮ P-020 恢复策略 ActionChain Y/N 矩阵

> **命名说明**: P-020 = Phase 020, 非 N## 编号。保留在 workflow topic 因其 Y/N 矩阵仍可复用。

> **触发条件** (任意一条即触发):
> - AI 写 scheduler/recovery_engine.py (ActionSpec / RecoveryActionChain / 失败重试逻辑)
> - 改 backend/scheduler/views.py RecoveryLog API (Serializer / ViewSet)
> - 改 backend/tasks/signals.py 触发 handle_task_failure (post_save + 防递归)
> - 写前端 Monitors/RecoveryLogTab.tsx (5 级颜色 + 过滤 + 详情 Modal)

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | ActionSpec dataclass 必填 4 字段: name/level/strategy/max_retries | | `grep "class ActionSpec" backend/scheduler/recovery_engine.py` |
| 2 | RecoveryActionChain.execute() 必捕获 step/task/app/device/system 5 层异常 | | `grep "except" backend/scheduler/recovery_engine.py` |
| 3 | RecoveryLog API 必含 level/strategy/action/result/duration 字段 | | `grep "class RecoveryLogSerializer"` |
| 4 | post_save 信号必须用 `update_fields` 防递归 (不传 update_fields 触发无限循环) | | `grep "update_fields" backend/tasks/signals.py` |
| 5 | RecoveryLogTab 必含 5 级颜色 (P0-P3 + INFO) + severity 过滤 + 详情 Modal | | `grep "severity.*P0" frontend/src/pages/Monitors/RecoveryLogTab.tsx` |
| 6 | 6 tests 覆盖: ActionSpec + RecoveryActionChain + 6 策略 (retry/skip/continue/fallback/restart/notify) | | `pytest scripts/tests/test_action_chain.py -v` |
| 7 | 4 tests 覆盖: RecoveryLog API list/filter/serializer | | `pytest scripts/tests/test_recovery_log_api.py -v` |

**AI 必做 (P-020 5 步闭环)**:
- ✅ **A: RecoveryLog API** → Serializer + ViewSet + URL + 4 tests
- ✅ **B: ActionChain 重构** → ActionSpec + RecoveryActionChain + 6 tests
- ✅ **C: 前端 RecoveryLog Tab** → 5 级颜色 + 过滤 + 详情 Modal + scheduler API
- ✅ **D: signals 触发** → post_save TaskExecution → handle_task_failure + 防递归
- ✅ **集成** → Monitors 页面集成 RecoveryLog Tab
- ❌ **NEVER 用 try/except 吞异常** (用户需要看错误链, recovery 必须捕获并记录到 RecoveryLog)
- ❌ **NEVER 不传 update_fields 触发 post_save** (防递归: 改 RecoveryLog 字段会触发 post_save → 又触发 recovery → 死循环)
- ❌ **NEVER 改 recovery_engine 不写 6 strategy tests** (6 策略是契约, 缺一即视为未闭环)

**同根因家族**: N82 (审计) + N100 (文件损坏) + N101 (状态不诚实) + **N116 (并发状态管理缺位)** —— 同根因 (恢复机制缺位)

### ㉗ N30 Skill SKILL.md 与 project_rules.md 章节漂移 Y/N 矩阵 (L1 可复用)

> **状态**: 索引已归档 (lesson 文件保留在 lessons/, Y/N 矩阵保留作参考)。N30 已被 N95 v9.0 真二分制 + N132 文档治理覆盖, 但 Y/N 检查项仍有参考价值。

> **触发条件** (任意一条即触发):
> - 修改 `project_rules.md` 任一章节 (§0/§1/§2/§3/§4/§5/§6/§6.4/§6.5)
> - 修订 N## 教训索引表 (§6.4)
> - 修订 §6.5 通用硬约束汇总
> - 决策树 `load_skills` 字段变更

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 修改 §0 执行宪法 → 同步 `gaf-orchestrator/SKILL.md` 决策树 step_0 | | grep `step_0` 在 gaf-orchestrator/SKILL.md |
| 2 | 修改 §3 Git 操作规范 → 同步 `gaf-orchestrator/SKILL.md` commit 分支 | | grep `commit` 在 gaf-orchestrator/SKILL.md |
| 3 | 修改 §4 变更操作规范 → 同步 `gaf-reflect-and-evolve/SKILL.md` 反思矩阵 | | grep `反思` 在 gaf-reflect-and-evolve/SKILL.md |
| 4 | 修改 §6.2 分级分发 → 同步 `gaf-lesson-router/SKILL.md` N95 引用 + 步骤 5 | | grep `L0/L1/L2` 在 gaf-lesson-router/SKILL.md |
| 5 | 修改 §6.4 N## 索引表 → 同步 `gaf-lesson-router/SKILL.md` taxonomy 表 | | 比对 N## 条目数一致 |
| 6 | 修改 §6.5 通用硬约束 → 同步全部 5 个 gaf-* SKILL.md | | grep 关键硬约束词 |
| 7 | 跑 `python scripts/bootstrap/sync_skills.py --check` 验证 5 份决策树副本一致 | | EXIT_CODE=0 |

**AI 必做 (N30 硬规则)**:
- ✅ 修改 project_rules.md 任一被 SKILL.md 引用的章节 (§0/§3/§4/§6/§6.4/§6.5) 时, 必须同步对应 gaf-* SKILL.md
- ✅ 修订 §6.2 分级分发时, 必须同步 `gaf-lesson-router/SKILL.md` 的 N95 引用和步骤 5
- ✅ 建议跑 `sync_skills.py --rules-drift-check` (待 TD 后续实现) 做双向校验
- ❌ NEVER 修改 project_rules.md 后直接 commit 不同步 SKILL.md 引用
- ❌ NEVER 让 rules 层与 SKILL 层漂移超过 1 个 commit

**反模式** (N30 来源):
- v8.5 修订 §6.2 但未同步 lesson-router/SKILL.md → AI 强制 5 层分发（v8.5 旧机制）, 违反 "L0 默认 1 层"
- 详见 lesson `2026-07-07-n30-skill-rules-drift.md` + arch-mistakes §54 + TD-020

## P2 自动归档 (治本机制 — 2026-08-22)

| N## | 原索引行 | 归档原因 |
|:---:|---------|---------|
| N106 | \| N106 \| SYNC_STATE 路径常量 \| 用 `SYNC_STATE` 常量, 不硬编码路径 \| `lessons/N106-sync-state-path.md` \| 3 \| 2026-06-16 \| | cap-clear: last=2026-06-16 cnt=3 |
| N91 | \| N91 \| pre-commit hook 失败 \| hook 失败 ≠ 任务失败 → 看 hook ID → 跑映射表修复命令; B2 大修改 3 门槛预处置 (evidence + spec-context + B2 --acknowledge); doc-sync skip 用 GAF_SKIP_DOC_SYNC=1 (非 commit token) \| `lessons/N91-m2b-hook-failure.md` \| 3 \| 2026-06-17 \| | cap-clear: last=2026-06-17 cnt=3 |
| N121 | \| N121 \| bypass weekly review \| bypass 审计日志每周 review, 不堆积 \| `lessons/N121-m2f-bypass-weekly-review.md` \| 3 \| 2026-06-17 \| | cap-clear: last=2026-06-17 cnt=3 |
| N123 | \| N123 \| ai-memory restructure \| .ai-memory/ 结构变更后跑 sync_ai_memory.py 重建索引 \| `lessons/N123-ai-memory-restructure.md` \| 1 \| 2026-06-21 \| | cap-clear: last=2026-06-21 cnt=1 |

## P2 自动归档 (治本机制 — 2026-08-22)

| N## | 原索引行 | 归档原因 |
|:---:|---------|---------|
| N129 | \| N129 \| 审计 3 棵代码树 \| 审计必搜 `backend/` + `agent/` + `frontend/`, 不只搜一个 \| `lessons/N129-audit-scope-must-be-comprehensive.md` \| 3 \| 2026-06-24 \| | cap-clear: last=2026-06-24 cnt=3 |
| N148 | \| N148 \| 双向控制消息路由标识 + Channels group 路由 \| 控制消息 payload 必含 agent_id (start AND stop); Channels group 用 Agent.agent_id string (非 DB pk) 路由 \| `lessons/N148-control-message-routing-and-db-pk-vs-business-id.md` \| 2 \| 2026-07-07 \| | cap-clear: last=2026-07-07 cnt=2 |
| N152 | \| N152 \| DRF 分页与前端数组期望不匹配 \| DRF ViewSet 必须显式声明 `pagination_class`; 后端返回形状、前端 TS 类型、组件取数方式必须一致 \| `lessons/N152-drf-pagination-array-mismatch.md` \| 2 \| 2026-07-09 \| | cap-clear: last=2026-07-09 cnt=2 |
| N146 | \| N146 \| ctypes.CDLL 热循环单例缓存 \| `ctypes.CDLL` 必须模块级单例缓存, 禁止热循环内反复 LoadLibrary/FreeLibrary (TD-011 ACCESS_VIOLATION) \| `lessons/N146-ldopengl-singleton-ctypes-hot-loop.md` \| 2 \| 2026-07-11 \| | cap-clear: last=2026-07-11 cnt=2 |
| N156 | \| N156 \| 写 Playwright E2E 测试前不读前端代码 → 假设端点错误 → 测试失败 \| 写 Playwright 前必 Grep 前端 store/api 层确认实际端点; "API 通过" ≠ "UI 通过"; 临时测试通过后持久化到 `scripts/e2e/scenarios/`; 测试失败先读代码不盲目重试 \| `lessons/N156-n147-test-before-understand.md` \| 3 \| 2026-07-11 \| | cap-clear: last=2026-07-11 cnt=3 |
| N159 | \| N159 \| 长任务子 agent 分发 (上下文预算根本解法) \| 复杂任务 (>1500 行 diff/跨模块/多缺陷) 必须拆分为多个子 agent 分发执行; 单对话上下文有限, 子 agent 分发是根本解法 \| `lessons/N159-long-task-subagent-delegation.md` \| 2 \| 2026-07-13 \| | cap-clear: last=2026-07-13 cnt=2 |
| N125 | \| N125 \| .trash/ 临时文件 \| 唯一临时目录 `.trash/`, 禁止子目录另建, 任务中不删除 \| `lessons/N125-trash-temp-staging.md` \| 5 \| 2026-07-13 \| | cap-clear: last=2026-07-13 cnt=5 |
| N158 | \| N158 \| LangGraph agent 实现层问题 \| LangGraph agent 实现需注意节点类型/状态管理/工具注册; 实现前必读 LangGraph 文档确认 API \| `lessons/N158-langgraph-agent-implementation.md` \| 3 \| 2026-07-14 \| | cap-clear: last=2026-07-14 cnt=3 |
| N161 | \| N161 \| 架构决策不应推卸给用户 + 计划内任务不停下问继续 \| 架构方案 A/B/C 由 AI 基于规则标准 (归一化/激进重构/长期最优) 直接决策, 不用 AskUserQuestion; 计划内任务完成后立即推进不停下; AskUserQuestion 仅用于规则未覆盖歧义/不可逆授权/真等价方案 \| `lessons/N161-n163-self-reliance-no-deferral.md` \| 3 \| 2026-07-14 \| | cap-clear: last=2026-07-14 cnt=3 |
| N160 | \| N160 \| 对话上下文预算管理 (E2E 逐次试错 + 工具输出未过滤 + 未用 N159 子 agent 分发) \| pytest 用 `-q` 非 `-v`; E2E 调试 ≤ 2 轮 (诊断脚本一次性 dump); 大文件用 offset+limit; ≥ 15 轮提示新开对话; 根本解法是 N159 子 agent 分发 \| `lessons/N160-n162-context-budget-command-reflection.md` \| 4 \| 2026-07-14 \| | cap-clear: last=2026-07-14 cnt=4 |
| N112 | \| N112 \| 后端字段→前端 4 步配套 \| 改后端字段必同步 TS/API/UI/Filter \| `lessons/N112-p024-frontend-sync.md` \| 4 \| 2026-07-15 \| | cap-clear: last=2026-07-15 cnt=4 |
| N174 | \| N174 \| TD 登记未验证修复方案 → 41% wontfix + 修复方向反转 \| TD 登记必填"修复方案验证"字段 (至少 1 个 grep 命令验证修复方向); grep 结果与方案矛盾时立即调整; wontfix 评估时先核查该字段; 详见 project_rules §4.8 \| `lessons/N174-td-registration-requires-fix-verification.md` \| 3 \| 2026-07-18 \| | cap-clear: last=2026-07-18 cnt=3 |

## P2 自动归档 (治本机制 — 2026-08-28)

| N## | 原索引行 | 归档原因 |
|:---:|---------|---------|
| N105 | \| N105 \| commit --no-verify 透传 bug \| 不用 `gaf-commit.sh --no-verify`, 直接 `git commit --no-verify` \| `lessons/N105-commit-bypass-rollback.md` \| 4 \| 2026-07-26 \| | cap-clear: last=2026-07-26 cnt=4 |

## 历史 lesson 文件索引补全 (TD-394 — 2026-08-24 反向孤儿审计)

> 以下 15 个 lesson 文件保留在 `lessons/` root，但此前未进入 failure-modes.md 或本文件
> 任何分级索引段，仅靠 lessons README Topic 表软检索 —— 违反"每个 lesson 文件应有索引记录"
> 一致性原则。TD-394 补登本表 (保留文件供软检索, 编号永不复用, 历史参考性质)。

| N## | 主题 | Lesson 链接 |
|----|------|------------|
| N95 | 规则发散 v8.4 早期教训 (真二分制) | `lessons/N95-distribution-gap.md` |
| N111 | 命令超时处理规范 | `lessons/N111-command-timeout.md` |
| N116 | 并发状态 + tier benchmark | `lessons/N116-m1g-concurrency-and-tier-benchmark.md` |
| N117 | 决策树 changelog 维护 | `lessons/N117-m1h-decision-tree-changelog.md` |
| N118 | M2A 43 测试机制 | `lessons/N118-m2a-43-tests.md` |
| N122 | scripts/ 脚本合并治理 | `lessons/N122-script-consolidation.md` |
| N124 | skill 删除与决策树同步 | `lessons/N124-skill-deletion-and-decision-tree-sync.md` |
| N131 | Playwright 浏览器自动化 | `lessons/N131-playwright-browser-automation.md` |
| N132 | DRF + React 踩坑 | `lessons/N132-drf-react-pitfalls.md` |
| N133 | 模拟器控制缺口 | `lessons/N133-emulator-control-gap.md` |
| N135 | 重构需浏览器登录验证 | `lessons/N135-refactor-needs-browser-login-verification.md` |
| N136 | URL 路由重复前缀 | `lessons/N136-url-routing-duplicate-prefix.md` |
| N137 | TS 6.0 erasable syntax 坑 | `lessons/N137-ts60-erasable-syntax-and-baseurl-deprecation.md` |
| N141 | 截图方法基准盲点 | `lessons/N141-screenshot-method-benchmark-blindspot.md` |
| N145 | login POC agent 无响应 | `lessons/N145-login-poc-agent-no-response.md` |

## P2 自动归档 (治本机制 — 2026-08-28)

| N## | 原索引行 | 归档原因 |
|:---:|---------|---------|
| N172 | \| N172 \| AI 思维链不主动用 subagent + 假沉淀 (用户每次都说"继续") \| 剩余 ≥ 2 个独立 TD 必主动用 subagent 并行 (search 评估 / general_purpose_task 修复); "应该沉淀" = 立即调用工具写文档, 非口头修辞; 详见 project_rules §3.6+§3.8 + dispatching-parallel-agents skill \| `lessons/N172-ai-proactive-subagent-and-real-sedimentation.md` \| 5 \| 2026-07-18 \| | cap-clear: last=2026-07-18 cnt=5 |
| N185 | \| N185 \| 测试覆盖盲区 = AI 思维链缺陷 (TD-336; 2026-07-22 OCR bug 排查暴露) \| AI 准备写测试修复前必评估"为什么测试没覆盖到" — 测试用例缺失? 测试场景设计缺陷? AI 思维链本身没识别到? 同类关键方法同步补单测; 详见 N182-N185 家族 lesson (N185 section) + TD-336 \| `lessons/N182-bug-investigation-three-dimensional-root-cause.md` (N185 section) \| 4 \| 2026-07-22 \| | cap-clear: last=2026-07-22 cnt=4 |
| N189 | \| N189 \| AI 把 "AI 主导开发必需的治理" 误判为 "过度治理" (2026-07-26 评估任务) \| "AI 主导开发" 模式治理复杂度 ≈ AI agent 框架复杂度, 是内在需求; N178 A3 判定增强: 数量多 ≠ 过度治理, 执行率低 + 无 evidence = 过度治理; 区分 AI 自我治理 (必需) vs 治理形式化 (应精简) \| `lessons/N189-ai-led-development-governance-necessity.md` \| 4 \| 2026-07-26 \| | cap-clear: last=2026-07-26 cnt=4 |
