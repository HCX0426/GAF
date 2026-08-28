---
spec_id: spec-66
title: TD-308 关闭 (A 方案 4.5x 加速验证通过, B 方案经 N167 评分不必要) + TD-309 wontfix (七维度评分 4 方案无明显领先)
status: ✅ done
created: 2026-07-21
owner: AI
priority: P1
related_tech_debt: [TD-308, TD-309]
n167_score: A=32/B=25 (TD-308-B 必要性评估, A 领先 7 分 → AI 自决不实施 B) + TD-309 4 方案 (A=29/B=26/G=30/wontfix=27, 最高 G 领先 wontfix 3 分 < 5 分阈值 → wontfix)
---

# spec-66: TD-308 关闭 + TD-309 评估

## 背景

spec-65 Phase 7 用户追问后实际验证通过:
- `pytest backend/ -n auto` → 1954 passed, 1 failed in 116.88s (526s→117s, 4.5x 加速)
- 失败的 1 个 test 单核也失败 → 与并行化无关, 已登记 TD-313
- TD-308 验证标准全满足: < 400s ✅ (117s) / < 600s ✅ / 循环模式可行 ✅

TD-308-B (slow 标记分层) 经 N167 七维度评分:
- 方案 A (不实施 B, 关闭 TD-308): 32/35
- 方案 B (实施 slow 标记): 25/35
- A 领先 7 分 (≥5) + 总分 32 ≥ 19 → AI 自决 A 方案

## Phase 1: N167 评分 TD-308-B 必要性 (✅ AI 自决)

- [x] 1.1 七维度评分 A vs B (见 frontmatter)
- [x] 1.2 A 领先 7 分 → AI 自决不实施 B, 关闭 TD-308

## Phase 2: 关闭 TD-308 (迁 active.md → fixed.md, 小修改) (✅)

- [x] 2.1 active.md TD-308 段落 (🚧 → ✅ FIXED, 加关闭注释)
- [x] 2.2 fixed.md 追加 TD-308 ✅ FIXED 段落
- [x] 2.3 active.md 顶部计数 9 → 8 → 7 (含 TD-309 wontfix)
- [x] 2.4 active.md 下一 spec 触发更新 (TD-313 接修)

## Phase 3: 评估 TD-309 (fixed.md 4596 行膨胀, 七维度评分) (✅)

- [x] 3.1 读 fixed.md 结构 (268 TD 段落, 4596 行, 472KB)
- [x] 3.2 七维度评分 A (季度分片 29) vs B (归档 26) vs G (索引 30) vs wontfix (27)
- [x] 3.3 评估结论: wontfix (最高 G=30 领先 wontfix 3 分 < 5 分阈值, 无方案满足 N167 自决条件; AI 工作流已适应 Grep+offset/limit)

## Phase 4: wontfix TD-309, 迁移到 fixed.md (✅)

- [x] 4.1 active.md TD-309 段落 (🔧 → ❌ wontfix, 加 wontfix 注释)
- [x] 4.2 fixed.md 追加 TD-309 wontfix 段落 (含 4 方案评分 + wontfix 理由)

## Phase 5: commit + 反思 (✅)

- [x] 5.1 git commit
- [x] 5.2 反思段

## 反思 (小修改 + 评估型 spec, 跑 4 问 + 状态标记)

### ① 4 问反思

1. **改了什么**: TD-308 关闭 (N167 评分 B 不必要) + TD-309 wontfix (4 方案评分无明显领先)
2. **为什么改**: TD-308-A 已 4.5x 加速验证通过, B 方案边际收益小; TD-309 分片方案 vs wontfix 无明显领先
3. **怎么验证**: N167 七维度评分 (A=32/B=25 TD-308-B; A=29/B=26/G=30/wontfix=27 TD-309) + active.md 顶部计数 + fixed.md 段落追加
4. **影响范围**: 文档治理, 不涉及代码; active.md 7 活跃 TD, fixed.md 270 段落

### ② 状态标记

- ✅ spec-66 done (TD-308 关闭 + TD-309 wontfix)
- ✅ N167 七维度评分 2 次自决 (TD-308-B A 领先 7 分; TD-309 wontfix 最高 G 领先 3 分不满足自决, 评估结论 wontfix)
- ✅ active.md 顶部计数同步 (9 → 8 → 7)
- ✅ fixed.md 段落追加 (TD-308 ✅ FIXED + TD-309 ❌ wontfix)

### ③ A/B/C 改进

- A: TD-309 wontfix 是合理结论 (AI 工作流已适应), 避免 over-engineering
- B: TD-309 可考虑加索引段 (方案 G, 30/35), 但收益不明确, 暂不实施
- C: 选 A (wontfix 当前, 留待 TD-310 评估时一并复查)
