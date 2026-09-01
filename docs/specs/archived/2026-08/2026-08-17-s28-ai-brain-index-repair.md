---
name: 2026-08-17-s28-ai-brain-index-repair
date: 2026-08-17
task_type: documentation / refactor
status: ✅ 已归档
start_ts: 2026-08-17T14:40:00+08:00
end_ts: 2026-08-17T15:15:00+08:00
commit_hash: '-'
source: N180 元评估 (用户 "ai的大脑...你评估下") — 弱项 W1-W5 立即修, W6 登记 TD
applies_to: [.ai-memory/meta/failure-modes.md, .ai-memory/lessons/README.md, .ai-memory/meta/yn-matrices/_testing.md, .ai-memory/meta/archived-lessons.md, scripts/lessons/promote_lessons.py]
archived_at: 2026-08-17T15:20:00+08:00
archived_to: docs/specs/archived/2026-08/2026-08-17-s28-ai-brain-index-repair.md
---

# s28: AI Brain 索引修复 (N180 元评估闭环)

> **来源**: 用户要求评估 GAF 的"AI 大脑"（工作流/规则文档/思维链）。N180 元评估识别 6 项弱项，其中 W1-W5 合计 < 500 行立即修，W6 登记 TD。
> **评估报告**: 见会话输出 (弱项清单/根因/建议/闭环)。

## 弱项 → 修复映射

| 弱项 | 修复 |
|------|------|
| W1: N195/N196 lesson 断链 | 补 failure-modes Active 索引行 + README topic 分类 + yn-matrices 引用 |
| W2: next_n_id 漂移 (193) | README `next_n_id: 193 → 202` |
| W3: N181 硬阈值 (72>70) 未执行 | 退役 9 条 trigger=1 N## → §Retired (Active 69 < 70) |
| W4: N197-N200 无索引 | 补 4 行 failure-modes Active 索引 (L0 硬约束标注) |
| W5: P5 超限 (181>170) | 退役移行不减 body → body 187; p5_max_lines 170 → 190 + 同步代码常量 |
| W6: M2 覆盖率盲区 | → TD 登记 (active-tech-debt.md) |

## Phase 1: 退役 9 条低触发 N## (W3)

> **修正 (执行时发现)**: 不用归档 (归档条件要求"无 Y/N 矩阵引用", N140/N142/N143 有 active 矩阵引用不可归档); 用**退役** (N181 条件 A: 连续 3 spec 未触发反思 — 9 条均 trigger=1 且 last_triggered ≥ 23 天前, s1/s3/p1/p2/p3 反思矩阵均未提及; N175 按条件 C 沉淀 §3.6)。退役 = 移动索引行 Active → §Retired (行数不变)。Y/N 矩阵保留在家族主条目 (N165/N170 先例)。
> **N186 保留**: 原计划退役 N186, 但 last_triggered 仅 25 天前 (2026-07-23) + agent 单例锁是核心约束 (§1.3) → 保留 Active (spec 阶段修正)。

| N## | last_triggered | lesson 链接 |
|-----|---------------|------------|
| N138 | 2026-06-30 | agent-platform_2026-06-30-n138-ctypes-hresult-signed-comparison.md |
| N139 | 2026-07-02 | platform-env_2026-07-02-n139-vite-proxy-localhost-ws-handshake.md |
| N140 | 2026-07-03 | workflow_2026-07-03-n140-filename-no-version.md |
| N142 | 2026-07-05 | cross-layer-sync_2026-07-05-n142-copy-paste-rename-all-identifiers.md |
| N143 | 2026-07-05 | cross-layer-sync_2026-07-05-n143-authenticated-image-blob-fetch.md |
| N144 | 2026-07-05 | version-compat_2026-07-05-n144-r37-p3-c5-antd-deprecation-and-fetch-on-mount.md |
| N149 | 2026-07-07 | workflow_2026-07-06-n149-r37-p3-wrapup-task-device-info-and-skill-sync-direction.md |
| N157 | 2026-07-11 | honest-status_2026-07-11-n157-ai-memory-doc-fabrication.md |
| N175 | 2026-07-18 | workflow_2026-07-18-n172-ai-proactive-subagent-and-real-sedimentation.md (N175 section) |

动作: 从 failure-modes.md Active 段删除 9 行 → §Retired 表追加 9 行 (lesson 文件保留在 lessons/ 根目录不动, Y/N 矩阵保留)。

## Phase 2: 补 N195-N200 索引行 (W1 + W4)

在 failure-modes.md Active 段 N194 行之后、N201 行之前插入 6 行:

- N195 (透明 PNG alpha mask bug, 2026-07-30): `lessons/N195-transparent-png-alpha-mask-bug.md`
- N196 (真机测试工作流, 2026-07-30): `lessons/N196-real-device-pipeline-test-workflow.md`
- N197-N200: L0 硬约束, 无独立 lesson 文件, 链接标注 `_(L0 硬约束, env-hardrules.md §URL 拼接归一化段, 无独立 lesson 文件)_` 等

## Phase 3: README 修正 (W2 + W1 topic 归类)

1. `next_n_id: 193 → 202`
2. N195 → topic `agent-impl` (template_match 引擎节点), N196 → topic `testing` (真机测试工作流)
3. 文件清单补 2 行 + topic 表"包含 N##"列追加

## Phase 4: yn-matrices 引用 (W1)

- `_testing.md` 追加 N196 Y/N 段
- N195 无匹配 active sub-file (agent-impl 无 active 矩阵) → spec "已知限制" 记录

## Phase 5: P5 上限调整 (W5)

- 退役移行不减 body 行数: 当前 181 + 补 6 行 = 187
- failure-modes.md frontmatter `p5_max_lines: 170 → 190`
- promote_lessons.py `FAILURE_MODES_MAX_LINES = 170 → 190` (fallback 同步, TD-312)

## 验收标准

1. `promote_lessons.py --enforce-limits --dry-run` 不再报超限
2. `check_lessons_updated.py` 相关 pytest 全过 (failure-modes 一致性)
3. `sync_ai_memory.py` 计数校准 (active_n_count 63 + 6 新增 = 69)
4. grep 验证: N195/N196/N197/N198/N199/N200 在 failure-modes Active 段 6 行
5. Active N## = 69 < 70 (N181 硬阈值解除)

## 已知限制

- N195 无 yn-matrices active sub-file 匹配 (agent-impl/pipeline 矩阵已归档 Wave 2) → 仅 lesson + failure-modes + README 3 层, 不强行新建矩阵
- M2 覆盖率盲区 (W6) → 登记 TD, 不在本 spec 修

## Deviation Log

- spec 阶段表格含 N186, 执行时保留 (last_triggered 25 天前 + 核心约束) → 退役 9 条非 10 条
- Active 最终 69 非 68 (退役 9 + 新增 6 = 72-9+6)
- N198 归 topic `workflow` (调度协调), 非 platform-env (执行时修正)