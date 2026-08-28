---
spec_id: spec-39
title: 小 TD 批量治理 (TD-278 修复 + TD-276/290/291 wontfix)
status: ✅ completed
created: 2026-07-20
last_updated: 2026-07-20
related: TD-276 (wontfix), TD-278 (fixed), TD-290 (wontfix), TD-291 (wontfix)
n167_score: N/A (小修改批量, < 50 行 diff per TD, 豁免 7 维度评分)
commit: -
---

# Spec-39: 小 TD 批量治理

> **触发**: AI 自决排序模式 (用户授权 2026-07-20) — spec-38 完成后, 排序剩余 TD, 选最小成本批量闭环 4 个 P3 小 TD

## §0 任务背景

spec-38 完成后, active.md 剩余 TD:
- TD-273 (P3, agent 字符串字面量状态比较, ~50 行)
- TD-276 (P3, executions N+1 风险, 审计类)
- TD-277 (P3, accounts 跨 app import, ~100 行)
- TD-278 (P3, generate-api-types 缺时间戳, < 30 行)
- TD-287 (P3, message_compressor 未接入, > 500 行)
- TD-288 (P3, AgentSelector 未接入 dispatch_task, ~50 行)
- TD-289 (P3, except Exception 372 处, > 500 行)
- TD-290 (P3, coord_transformer per-monitor TODO, 审计类)
- TD-291 (P3, screenshot_retention_gb placeholder, 审计类)

**spec-39 范围** (批量小 TD, 4 个 P3):
- TD-278: 修复 (generate-api-types.js 加时间戳头)
- TD-276: wontfix 审计 (executions list 无 N+1)
- TD-290: wontfix 审计 (coord_transformer 当前实现工作)
- TD-291: wontfix 审计 (placeholder 是合法 feature 占位)

**剩余 TD 排序** (下一 spec 候选):
- spec-40: TD-273 + TD-288 (agent enum + AgentSelector 接入, ~300 行中修改)
- spec-41: TD-277 (accounts 跨 app import 解耦, ~100 行)
- spec-42 (大): TD-287 (message_compressor 接入, > 500 行)
- spec-43 (大): TD-289 (except Exception 372 处, > 500 行)

## §1 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | TD-276/290/291 审计 + wontfix 决策 | ✅ | 2026-07-20 | - | 3 个 TD 全 wontfix (EVALUATED); grep 验证 |
| Phase 2 | TD-278 修复 (generate-api-types.js 加时间戳头) | ✅ | 2026-07-20 | - | `// Generated at YYYY-MM-DD` header 逻辑; readFileSync/writeFileSync import |
| Phase 3 | 文档同步 + commit + hash 回填 | ✅ | 2026-07-20 | - | fixed.md TD-278 + wontfix.md TD-276/290/291 + active.md 4 closed 注释 |

## §2 N167 评分

**豁免理由**: 小修改批量 (TD-278 修复 < 30 行 diff; TD-276/290/291 是 wontfix 审计, 0 行代码改动). 按 §2.0.5 分级触发: 小修改 (typo/1-3 行/配置调整) 豁免 7 维度评分. 本 spec 总 diff < 50 行, 走小修改路径.

## §3 Phase 1: TD-276/290/291 审计 + wontfix 决策

### TD-276 审计 (executions list N+1 风险)

**审计命令**: `grep "s\.execution[^_]" backend/executions/views.py` = 0 处

**审计结论**:
- 循环代码只访问 `s.execution_id` (FK _id 字段, 不查 DB) 和 `s.started_at`/`s.completed_at`/`s.status` (本地字段)
- 未访问 `s.execution.<field>` (FK 跳转, 触发 DB 查询)
- Django ORM `_id` 后缀字段是直接存储的 FK 值, 不触发 DB
- **决策**: ❌ EVALUATED (wontfix) — 不是 N+1, 无需 select_related

### TD-290 审计 (coord_transformer per-monitor TODO)

**审计命令**: `grep "TODO" agent/src/utils/coord_transformer.py` = 2 处 (L33 + L114)

**审计结论**:
- 当前实现用 `display_builder` 比较 client rect 设置 `display_id`, 单显示器 + 多显示器窗口化场景下工作正常
- 多显示器 fullscreen 场景坐标可能不准 — 但 BD2-AUTO 也未完全解决
- GAF 当前不支持 agent 主动 multi-monitor fullscreen, 不触发该 TODO
- TODO 触发条件是 "when fullscreen support lands", 不是 "现在就修"
- **决策**: ❌ EVALUATED (wontfix) — 当前实现工作; 多显示器 fullscreen 是后续 feature

### TD-291 审计 (screenshot_retention_gb placeholder)

**审计命令**: `grep "screenshot_retention_gb" frontend/src/types/api.generated.ts` 命中

**审计结论**:
- `screenshot_retention_gb` 是 `UnattendedStrategy` schema 中的合法字段, 用于未来实现 screenshot 定期清理的容量上限
- 当前不实现是独立 feature (需 backend 后台任务 + 配置 UI + migration), 不是 bug
- schema 中保留字段是为了前端 type 提前对齐 (与 debug_mode/wait_when_background 一致)
- **决策**: ❌ EVALUATED (wontfix) — placeholder 是合法 feature 占位

## §4 Phase 2: TD-278 修复

### 修改文件

**`frontend/scripts/generate-api-types.js`** (TD-278 修复):
- import 加 `readFileSync, writeFileSync` from `node:fs`
- main 函数末尾加 timestamp header 逻辑:
  - 读 `outputFile` (`api.generated.ts`) 内容
  - 若首行不以 `// Generated at ` 开头 → prepend `// Generated at YYYY-MM-DD from OpenAPI schema (run: npm run generate:api-types)\n`
  - 若已有 header → 原地替换首行 (避免重复 header 堆积)

### 验证

- 重跑 `npm run generate:api-types` 后 `api.generated.ts` 首行为 `// Generated at 2026-07-20 from OpenAPI schema (run: npm run generate:api-types)`
- 重复 generate 不堆积 header

## §5 Phase 3: 文档同步 + commit + hash 回填

### 文档同步清单

- `docs/general/tech-debt/active.md`: 删除 TD-276/TD-278/TD-290/TD-291 段落 (TD-278 在 spec-39 修复前从未登记到 active.md, 因 spec-53 commit 时直接登记; TD-276/290/291 段落删除) + 加 4 行 closed 注释
- `docs/general/tech-debt/fixed.md`: 加 TD-278 ✅ FIXED 段落
- `docs/general/tech-debt/wontfix.md`: 加 TD-276/290/291 ❌ EVALUATED 段落 (3 个)
- `docs/general/completed-features.md`: 加 C-084
- `docs/general/pending-roadmap.md`: 加 P-025

### commit

```bash
git add frontend/scripts/generate-api-types.js \
        docs/general/tech-debt/active.md \
        docs/general/tech-debt/fixed.md \
        docs/general/tech-debt/wontfix.md \
        .trae/specs/2026-07-20-spec39-small-td-batch.md \
        docs/general/completed-features.md \
        docs/general/pending-roadmap.md \
        .trae/specs/2026-07-20-spec38-hook-maintainer-mode-differentiation.md
git commit -m "fix(spec-39): TD-278 generate-api-types timestamp + TD-276/290/291 wontfix (spec-38 hash backfill)"
```

### hash 回填

按 N176 单对话批量 spec 单 commit 硬约束:
- 本次 commit 完成后, spec-38 文件已在本 commit 回填 (- 在 spec-38 commit 后未回填, 合并到 spec-39 commit 一起回填)
- spec-39 commit hash 留空, 由下次 spec commit 时一并回填 (follow-up edit, 不 commit)

## §6 反思 (小修改级别 — 4 问 + 状态标记)

### 4 问反思

1. **本轮要做什么? 范围边界是什么?**
   - 修复 TD-278 (generate-api-types 时间戳) + 审计 3 个 TD 决策 wontfix
   - 边界: 不动 agent/backend 业务代码; 不修 TD-273/277/287/288/289

2. **现有代码中哪些可以直接复用? 哪些需要修改?**
   - 复用: generate-api-types.js 现有 spawn/openapi-typescript 逻辑不变
   - 修改: 加 import + main 函数末尾加 header 逻辑

3. **有什么潜在风险或依赖?**
   - 风险: 若 `api.generated.ts` 文件不存在, readFileSync 会抛错 — 但该文件是 openapi-typescript 生成的, 必然存在
   - 依赖: 无 (header 逻辑独立于 schema 生成)

4. **本轮的验收标准是什么?**
   - TD-278: generate-api-types.js 跑后 api.generated.ts 首行有时间戳
   - TD-276/290/291: wontfix 段落写入 wontfix.md + active.md 加 closed 注释
   - 全部 ✅

### 状态标记

- 本轮新增功能状态标记是否已更新? Y (fixed.md TD-278 + wontfix.md 3 个 TD + active.md closed 注释 + C-084 + P-025)
- 三态定义: 不涉及 ✅ 可用 / 🔧 代码存在 / ❌ 未实现 (本 spec 是 wontfix + fixed, 不涉及功能状态)
- 跑 `git status` + `git diff --stat` 看本轮新增文件, 确认对应文档已更新

## §7 与 §3.6 自决排序模式的关系

本 spec 是用户授权 "做完一个任务自己排剩余优先级" 后的第 1 个 spec (spec-38 是授权前的最后一个). 按 §3.6:
- spec-39 完成后, AI 自决排序剩余 TD:
  - P3 同优先级按登记时间排序: TD-273 (2026-07-19) → TD-277 (2026-07-19) → TD-287 (2026-07-20) → TD-288 (2026-07-20) → TD-289 (2026-07-20)
  - 排除已闭环: TD-276/278/290/291 (spec-39 闭环)
  - 推荐下一 spec: **spec-40 (TD-273 + TD-288)** — 两个 agent 相关 TD 合并, ~300 行中修改, 同 app (agent) 内聚
  - 备选: spec-41 (TD-277) 单独 ~100 行; spec-42 (TD-287) > 500 行大修改; spec-43 (TD-289) > 500 行大修改
- 自决推进: spec-40 立即开 (不等用户确认, §3.6 强触发)
