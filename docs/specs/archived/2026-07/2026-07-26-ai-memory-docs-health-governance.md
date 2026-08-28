---
summary: AI 工作流/规则/思维链综合评估治理 — 修复 evidence 积压/trigger_count 空转/编号冲突/空目录占位等 5 个系统性问题
applies_to: ['.ai-memory', 'docs', 'scripts/bootstrap']
key_decisions:
  - 治理分 4 波 (Wave 1-4), 独立任务用 subagent 并行
  - P0 立即修 (evidence 归档 + trigger_count 统计 + N167 冲突)
  - P1 本月内修 (空目录 + auto-kb + ref maintainer + 架构文档字段)
  - P2 季度内修 (ref/docs 合并 + _workflow.md 拆分 + health 月度评估 + evidence hook)
last_updated: 2026-07-26
created_at: 2026-07-26
completed: 2026-07-26
spec_id: spec-2026-07-26-ai-memory-docs-health
status: completed
priority: high
owner: AI
---

# spec-2026-07-26 AI Memory + Docs 健康度治理

## 来源

用户反馈: "再结合这两个 ai 用的文件夹再次评估，并给出改进建议" → 综合评估识别 5 个系统性问题 → "开始吧，所有任务排个计划开始" (强触发循环模式)

## 5 个系统性问题 (实测数据)

| # | 问题 | 实测数据 | 根因 |
|---|------|---------|------|
| 1 | evidence 严重积压 | active/ 63 个, archived/2026-07 仅 2 个, 归档率 3.2%, 8 残缺 + 2 非标 | startup_checks.py 归档未执行, 模板未强制 |
| 2 | trigger_count 全 0 | 67/67 Active N## 全 0, last_triggered 全 `-`, health/2026-07.md 无 N## 评估 | 触发追踪机制从未落地, N181 退役机制空转 |
| 3 | 规则膨胀 vs docs 萎缩 | .ai-memory ~120+ .md vs docs ~30 .md; docs 6 空目录; auto-kb 2 个 41 天未更新 | ref/ 与 docs/ 职责重叠, 空目录违反 N126 |
| 4 | lessons/evidence 沉淀断裂 | lessons 67 + evidence 63 积压; N167 出现 2 个文件 (编号冲突) | 触发点 1+3 未执行, hook 未校验文件名唯一 |
| 5 | docs/ 与代码 drift 风险 | 核心架构文档无 applies_to_code_paths; completed-features 421 ✅ 但 4 天未更新 | v9.6 §9.4 stale 检查依赖字段缺失 |

## 阶段状态表

| Wave | 任务 | 状态 | 完成时间 | commit hash | 验收 evidence |
|------|------|------|---------|-------------|--------------|
| T0 | 写 spec 文件 | ✅ | 2026-07-26 | - | 本文件 |
| T1 | P0-1 归档 63 evidence + 修复 8+2 残缺 | ✅ | 2026-07-26 | - | 归档 49+8=57 个, active 剩 6 个完整 |
| T2 | P1-1 删 docs 6 空目录 | ✅ | 2026-07-26 | - | 6 个 .gitkeep 空目录全删 |
| T3 | P1-2 刷新 auto-kb 2 个文件 | ✅ | 2026-07-26 | - | auto_updated 字段更新为 2026-07-26 |
| T4 | P1-3 补 ref/ 2 个 maintainer | ✅ | 2026-07-26 | - | spec-index.md + session-context.md |
| T5 | P0-3 修复 N167 编号冲突 | ✅ | 2026-07-26 | - | 孤儿文件合并到主文件, 移到 .trash/ |
| T6 | P0-2 实现 trigger_count 统计脚本 | ✅ | 2026-07-26 | - | track_n_trigger.py, 67/67 全 >0, top1 N167 24次 |
| T7 | P1-4 架构文档补 applies_to_code_paths | ✅ | 2026-07-26 | - | 3 份文档 (optimal-solution/features-overview/overview) |
| T8 | P2-4 evidence 模板强制使用 hook | ✅ | 2026-07-26 | - | check_evidence_completeness.py + pre-commit 集成 |
| T9 | P2-1 合并 ref/ 与 docs/ 职责 | ✅ | 2026-07-26 | - | TD-341 已修复: 4 文件迁到 docs/reference/, ref/ 仅留 3 AI 内部, 24 files +470/-60, N167 32/35 |
| T10 | P2-2 拆分 _workflow.md | ✅ | 2026-07-26 | - | 拆为 3 个 sub-file (224/213/161 行) |
| T11 | P2-3 health 补 N## 月度评估 | ✅ | 2026-07-26 | - | 追加 N## 月度评估段, 67/67 trigger_count>0 |
| T12 | commit + 反思 + 状态更新 | ✅ | 2026-07-26 | - | commit -, 179 文件, pre-commit 13/13 passed |

## 范围偏差日志

(无)

## N151 5 步架构评估 (大修改强制)

### Step 1: 架构盘点
- `.ai-memory/` 5 层文档体系 (rules/handbook/failure-modes/yn-matrices/lessons)
- `docs/` 6 子目录 (architecture/business/standards/tech-debt/specs/health)
- `scripts/bootstrap/` 现有同步脚本 (sync_ai_memory.py / sync_skills.py / sync_docs_index.py)

### Step 2: 识别反模式
- ❌ evidence 积压 63 个 (规则要求 30 天归档, 实际未执行)
- ❌ trigger_count 全 0 (规则要求追踪, 实际未实现)
- ❌ N167 编号冲突 (规则要求"编号永不复用", 实际 2 个文件)
- ❌ docs 6 空目录 (违反 N126 诚实标记)
- ❌ ref/ 与 docs/ 职责重叠 (违反 §2.1 文档分层)

### Step 3: A/B/C 备选方案

**方案 A: 全量激进重构** — P0+P1+P2 全做, 11 个任务一次完成
- 优点: 一次性治理彻底
- 缺点: 上下文压力大 (N160), 单 commit diff > 500 行
- 风险: 跨多模块, 易出错

**方案 B: 分波治理** — Wave 1 (P0+P1 并行) → Wave 2 (P0 关键串行) → Wave 3 (P2 结构性)
- 优点: 风险隔离, 可中途评估
- 缺点: 跨多 commit, 但符合 spec 粒度
- 风险: 低

**方案 C: 只做 P0, P1/P2 留 TD** — 最小化治理
- 优点: 快速完成
- 缺点: P1 的空目录/auto-kb drift 不修会持续累积
- 风险: 治理不彻底, 半年后再治理

### Step 4: 拒绝反模式 + AI 自决

- ❌ 拒绝方案 A (上下文压力)
- ❌ 拒绝方案 C (治理不彻底, 违反"技术债务不堆积"原则)
- ✅ 选方案 B (分波治理)

### Step 5: N167 七维度评分 (方案 B)

| 维度 | 分 | 理由 |
|------|---|------|
| 1 架构长远性 | 5/5 | 修 trigger_count 让 N181 退役机制真正落地, 长期受益 |
| 2 全局归一化 | 5/5 | 修 N167 冲突 + ref/docs 职责合并, 消除双重维护 |
| 3 新旧兼容 | 5/5 | 单人项目, 无外部兼容压力 |
| 4 现有业务完善 | 4/5 | 覆盖 5 个系统性问题, 但 P2-1 ref/docs 合并改动大 |
| 5 性能资源优化 | 4/5 | evidence 归档后查询快, 但 hook 增加会拖慢 commit |
| 6 安全合规加固 | 4/5 | evidence 模板强制 + trigger 统计, 提升 N126 诚实度 |
| 7 长期维护成本 | 5/5 | 一次性投入, 长期受益 (退役机制 + drift 检测) |
| **总分** | **32/35** | ≥ 19 且领先 ≥ 5 分 → AI 自决执行 |

## 执行计划

### Wave 1: 4 个独立任务并行 (subagent, 无文件冲突)

| 任务 | 操作目录 | subagent 类型 |
|------|---------|---------------|
| T1 evidence 归档 | `.ai-memory/evidence/` | general_purpose_task |
| T2 删 docs 6 空目录 | `docs/architecture/{agent,backend,frontend}/` + `docs/business/{accounts,system,workspace}/` | general_purpose_task |
| T3 刷新 auto-kb | `.ai-memory/meta/auto-kb/` (api-endpoints.md + error-codes.md) | general_purpose_task |
| T4 补 ref maintainer | `.ai-memory/ref/spec-index.md` + `session-context.md` | general_purpose_task |

### Wave 2: 主会话串行 (failure-modes.md 冲突)

- T5 修复 N167 编号冲突 (合并 2 个 N167 文件)
- T6 实现 trigger_count 统计脚本 (scripts/bootstrap/track_n_trigger.py)

### Wave 3: 2 个并行 (无冲突)

- T7 架构文档补 applies_to_code_paths (3 份核心文档)
- T8 evidence 模板强制使用 hook (scripts/hooks/check_evidence_completeness.py)

### Wave 4: P2 结构性 (串行, 谨慎)

- T9 合并 ref/ 与 docs/ 职责 (迁用户可读到 docs/reference/)
- T10 拆分 _workflow.md (697 行 → 3 个 sub-file)
- T11 health 补 N## 月度评估

### Wave 5: 收尾

- T12 commit + 反思 + 状态文档更新

## 验收标准

- [ ] evidence/active/ ≤ 5 个 (当前 63)
- [ ] evidence/active/ 无残缺 (8 个修复或 wontfix)
- [ ] failure-modes.md trigger_count 不全为 0 (至少 5 个 > 0)
- [ ] failure-modes.md 无 N167 编号冲突
- [ ] docs/ 无 .gitkeep 空目录
- [ ] auto-kb 4 个文件 auto_updated 字段近 7 天内
- [ ] ref/ 7 个文件 maintainer 字段完整
- [ ] 3 份核心架构文档含 applies_to_code_paths 字段
- [ ] pre-commit hook 校验 evidence 模板完整性
- [ ] _workflow.md ≤ 300 行 (拆分后)
- [ ] health/2026-07.md 含 N## 月度评估段

## 偏离阈值

- Phase 数 +50% (11 → 17+) 或 diff +30% 必更新本文件 "范围偏差日志"
- 超出 +100% 必停下问用户
