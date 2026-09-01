---
spec_id: spec-88
title: TD-336 — bug 排查三维根因评估规则体系补全 (4 新 N## + 3 强化 + 5 文档)
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-336]
related_n: [N182, N183, N184, N185, N150, N167]
depends_on: []
blocks: []
priority: P1
size: 大 (4 新 N## 5 层分发 + 3 强化 + 5 文档补全, 跨 8+ 文件, ~800 行 diff)
---

# spec-88: TD-336 — bug 排查三维根因评估规则体系补全

## 背景与问题

### 根因分析

2026-07-22 OCR bug 排查 (`_get_image` 缺 device fallback) 暴露规则体系留白:
AI 默认走"最短路径" (直接定位 fail 节点 + 写测试修复), 经用户三次提示才扩展到
链路归一化评估 + AI 思维链/工作流/规则文档三维评估。

**现有规则体系盲区** (详见 [N182 lesson](file:///d:/code/GAF/.ai-memory/lessons/workflow_2026-07-22-n182-bug-investigation-three-dimensional-root-cause.md)):
- N151 限大修改, bug 修复不触发
- N167 bug 修复跑维度 1/4, 未要求维度 2 (归一化)
- N150 只覆盖"同类问题在其他文件", 未覆盖上下游节点归一化
- N166 限任务完成后扫描, bug 排查启动不触发
- N174 只验证代码层 grep, 不评估三维根因

**12 项缺失规则** 分三维 (规则文档 5 + 工作流 3 + AI 思维链 4), 详见 [TD-336 active.md](file:///d:/code/GAF/docs/general/tech-debt/active.md#L170)。

### 目标

补全 bug 排查启动阶段的规则体系留白:
- 4 新 N## (N182-N185) 5 层分发完整
- 3 已有规则强化 (N150/N167/§4.8)
- 5 规则文档补全 (agent 引擎节点层整体留白)

## 修复方案

### 1. 新 N## (4 个, 5 层分发)

| N## | 主题 | 触发 | 必做 |
|:---:|------|------|------|
| N182 | bug 排查链路归一化评估 | bug 排查启动 (动手前) | 评估 fail 节点上下游归一化, 不只看 fail 节点本身 |
| N183 | bug 修复三维根因评估 | bug 修复 commit 前 / TD 登记 | TD 模板加"三维根因"必填字段 (代码层 + 工作流层 + 规则层) |
| N184 | 节点观测性硬约束 | 节点实现 / fail_result 返回 | 错误日志 + 上下文追溯, 禁止静默吞错 |
| N185 | 测试覆盖盲区 = AI 思维链缺陷 | AI 准备写测试修复前 | 评估"为什么测试没覆盖到", 归因到 AI 思维链层 |

**5 层分发** (每个 N##):
1. `lessons/workflow_2026-07-22-nNNN-*.md` — 完整 lesson 文件
2. `meta/failure-modes.md` §Active — 索引行 (1 行)
3. `meta/ai-operating-handbook.md` Part 2 — 行为红线 (1 行)
4. `meta/yn-matrices/_workflow.md` — Y/N 矩阵
5. `rules/project_rules.md` — 硬约束段落

**N182 现状**: 已有 lesson + failure-modes.md 索引 (2 层, commit `-`), 缺 3 层 (handbook + yn-matrices + project_rules)。

### 2. 强化已有规则 (3 个)

- **N150** (§3.3): "同类问题在其他文件" → 加"上下游节点链路归一化"
- **N167** (§2.0.5): bug 修复触发维度 1/4 → 加维度 2 (归一化) → 必跑 1/2/4/7
- **§4.8 TD 模板**: 新增"三维根因评估"必填字段 (代码层 + 工作流层 + 规则层)

### 3. 规则文档补全 (5 项, agent 引擎节点层整体留白)

1. `pipeline-authoring-guide.md` §2 节点表加 3 列: 截图模式 / 前置节点要求 / 能力边界
2. `testing-conventions.md` §1 三层表扩为四层 (加 agent 节点测试层) + 新增 §7 agent 节点测试规范
3. `project_rules.md` §4.9 N177 分级测试表加"agent chain e2e"行
4. `project_rules.md` §2.0 新增小节: 节点截图获取策略归一化
5. `project_rules.md` §2.0 新增小节: 节点契约文档化

## 实施计划 (subagent 拆分, 避免文件冲突)

### Phase 1: subagent A — 3 个新 lesson 文件 (N183/N184/N185)
- 创建 `.ai-memory/lessons/workflow_2026-07-22-n183-bug-fix-three-dimensional-root-cause.md`
- 创建 `.ai-memory/lessons/workflow_2026-07-22-n184-node-observability-hard-constraint.md`
- 创建 `.ai-memory/lessons/workflow_2026-07-22-n185-test-coverage-blindspot-ai-thinking.md`
- 参考 N182 lesson 格式 (frontmatter + 6 sections)

### Phase 2: subagent B — 5 层分发索引层 (3 个独立文件)
- `failure-modes.md` §Active 加 N183/N184/N185 索引行
- `ai-operating-handbook.md` Part 2 加 N182/N183/N184/N185 行为红线
- `yn-matrices/_workflow.md` 加 N182/N183/N184/N185 Y/N 矩阵

### Phase 3: subagent C — 规则文档补全 (2 个独立文件)
- `pipeline-authoring-guide.md` §2 节点表加 3 列
- `testing-conventions.md` §1 三层表扩四层 + 新增 §7

### Phase 4: 主会话 — project_rules.md 强化 (避免与 subagent 冲突)
- N150 强化 (§3.3)
- N167 强化 (§2.0.5)
- §4.8 TD 模板加三维根因字段
- §4.9 N177 加 agent chain e2e 行
- §2.0 新增 2 小节 (截图归一化 + 契约文档化)
- N182-N185 新 N## 段 (引用 lesson)

### Phase 5: 主会话 — active.md 迁出 + commit + hash 回填
- TD-336 段落从 active.md 迁到 fixed.md
- active.md 计数更新
- commit + spec-88 hash 回填

## 验收标准

- [ ] 4 个新 N## 在 5 层分发完整 (lesson + failure-modes + handbook + yn-matrices + project_rules)
- [ ] 3 个强化规则在 project_rules.md 对应位置文本更新
- [ ] 5 项规则文档补全 (pipeline-authoring-guide + testing-conventions + project_rules §4.9/§2.0)
- [ ] pre-commit hook 全通过 (gaf-governance-batch 12/12 + B2 + spec_id + N105)
- [ ] sync_ai_memory.py 跑通无 conflict
- [ ] active.md TD-336 段落迁到 fixed.md
- [ ] active_n_count 61 → 64 (N182 已计, 加 N183/N184/N185)

## N151 5 步架构视角 (大修改必跑)

1. **盘点**: 4 新 N## + 3 强化 + 5 文档, 跨 8+ 文件
2. **识别反模式**: 无反模式 (补全规则留白, 非重构)
3. **A/B/C 方案**:
   - A: 一次性全改 (本 spec 方案, subagent 并行)
   - B: 分 4 spec (每 N## 一个, 过度拆分)
   - C: 只补 N182-N185 不强化已有 (治标不治本)
4. **拒绝反模式**: 选 A (N159 subagent 并行 + N175 落地检查清单)
5. **AI 自决**: A 方案, 基于 N159 (大修改必拆 subagent) + N175 (落地检查)

## N167 7 维度评估

1. **根因修复**: ✅ 补全 12 项缺失规则
2. **全局归一化**: ✅ N182 本身就是归一化评估规则
3. **性能影响**: N/A (纯文档/规则)
4. **同根因扫描**: ✅ 3 强化覆盖已有规则范围盲区
5. **测试覆盖**: N/A (规则文档, 非代码)
6. **文档同步**: ✅ 5 层分发 + 5 文档补全
7. **架构长远**: ✅ 填补 agent 引擎节点层整体留白
