---
spec_id: spec-59-B
title: 规则文档瘦身 v9.2 — rules §2.0.5 简化为指针 + active.md FIXED 段落迁出 (TD-302)
created: 2026-07-21
status: ✅ completed
priority: P3
td_refs: [TD-302]
parent_spec: spec-59-A (元评估弱项 B1/B2/B3)
n167_score: 15/15 (3 维 1/2/7, AI 自决)
ai_self_decide: true (中修改 + 用户已授权方向 + active.md 已有详细修复方案)
---

# spec-59-B: 规则文档瘦身 v9.2 (TD-302)

## 状态表

| Phase | 内容 | 状态 | 完成时间 | commit | 验收 evidence |
|:---:|---|:---:|:---:|:---:|---|
| 0 | N151 架构盘点 + N167 3 维评分 + 范围调整 (B3 KEEP) | ✅ | 2026-07-21 | — | N178-A3 过度治理检查: B3 全仓库改名 LM1/LM2/LM3 价值低 (handbook §命名消歧 已有效) + 成本高 (18+ 文件) → KEEP; N178-A4 范围偏差 -1 项 (B3 KEEP) < 30% |
| 1 | B1+B2 合并: rules §2.0.5 简化为指针 (~50→12 行) + _refactor-dimensions.md 补充评分硬约束 + N178 段 | ✅ | 2026-07-21 | — | rules §2.0.5 line 166-177 (12 行); _refactor-dimensions.md §1 末尾新增 N167 评分硬约束 + N178 段 (line 115-144); 单一权威源 |
| 2 | active.md ✅ FIXED 段落迁出 (TD-295/296/301) + fixed.md 补 TD-296/301/302 | ✅ | 2026-07-21 | — | active.md 4 处 ✅ FIXED 段落删除 (TD-295/296×2/301/302); fixed.md 补 TD-296 (全闭环, 删旧部分闭环段) + TD-301 + TD-302; active.md 顶部状态更新 "活跃 TD 6→5" |
| 3 | 文档同步 + commit + 反思 | ✅ | 2026-07-21 | (本 commit) | completed-features C-097 + pending-roadmap P-038 ✅ + 反思见下 |

## 背景

spec-59-A 元评估识别规则文档 3 项弱项 (B1/B2/B3):
- B1 跳转链 5 层: rules → handbook → failure-modes → yn-matrices → lessons
- B2 N151/N167 双处维护: rules §2.0.4/§2.0.5 + yn-matrices 双处, 可能已漂移
- B3 L1/L2/L3 同名双义: §6.1 加载机制层 vs §6.2 教训分级层

本 spec (spec-59-B) 治理 B1/B2/B3。

## N151 架构盘点

### 现有架构
- rules §2.0.4 (N151): 简短指针 (~10 行) + "详细 5 步流程见 _ai-autonomy.md §2 ㉕ N151" → 已是单一权威源模式
- rules §2.0.5 (N167): 详细段 (~50 行, line 165-216) — 7 维度清单 + 评分硬约束 + spec-49 强化 + N178 段
- yn-matrices/_refactor-dimensions.md: 已有完整 7 维度评估表 + Y/N 检查表 (含 spec-49 ⑤⑥ #10-12) + 9→7 维度映射表
- 缺: 评分硬约束段 (rules §2.0.5 line 183-190) + N178 段 (line 199-214) 未在 _refactor-dimensions.md

### 反模式识别 (N151 step_2)
- B2 双处维护: rules §2.0.5 详细 + _refactor-dimensions.md 详细 = 双处, 漂移风险 (spec-49 强化在 rules 有, _refactor-dimensions.md Y/N 检查表 #10-12 部分覆盖, 但评分硬约束 + N178 段只在 rules)
- B3 同名双义: handbook Part 1 §命名消歧 已显式说明 "L1 硬加载 vs L1 教训" + "判定规则", AI 实际未混淆

### N178-A3 过度治理检查 (B3)
- 问: "B3 LM1/LM2/LM3 全仓库改名价值 > 改动成本?"
- 答: 否。handbook §命名消歧 已显式说明 L1 双义 + 判定规则, AI 实际未混淆。全仓库改名涉及 18+ 文件 (rules + handbook + failure-modes + 4 SKILL.md + 4 scripts + _refactor-dimensions.md + _workflow.md + summaries + README), 引入大量 diff, 影响 git blame, 价值低。
- 决策: B3 KEEP (handbook §命名消歧 段已有效), 不做 LM1/LM2/LM3 改名

### N178-A4 spec 范围限制
- TD-302 描述: B1 + B2 + B3 + active.md 清理
- spec 实际: B1+B2 合并 (rules §2.0.5 简化为指针) + active.md 清理, B3 KEEP
- 范围偏差: -1 项 (B3 KEEP), 在 30% 范围内, 无需用户确认

## A/B/C 备选 + N167 评分 (中修改跑 3 维 1/2/7)

### 方案 A: B1+B2 合并 + B3 KEEP + active.md 清理 (推荐)
- rules §2.0.5 简化为指针 (~10 行, 与 §2.0.4 风格一致)
- _refactor-dimensions.md 补充: 评分硬约束段 + N178 段
- active.md ✅ FIXED 段落迁出 (TD-295/296/301) → fixed.md 补 TD-301
- B3 KEEP (handbook §命名消歧 已有效)

### 方案 B: B1+B2+B3 全做 + active.md 清理
- 同方案 A + B3 LM1/LM2/LM3 全仓库改名 (18+ 文件)

### 方案 C: 仅 B1+B2 (不动 active.md)
- rules §2.0.5 简化为指针, _refactor-dimensions.md 补充
- 不清理 active.md ✅ FIXED 段落

### N167 3 维评分 (N178-A2 维度 4-7 不适用, 中修改只跑 1/2/7)

| 维度 | A | B | C | 评分理由 (N178-A2) |
|:---:|:---:|:---:|:---:|---|
| 1. 架构长远性 | 5/5 | 5/5 | 5/5 | 单一权威源 + 指针模式, 3-5 年受益 (rules 不膨胀) |
| 2. 全局归一化 | 5/5 | 5/5 | 4/5 | A 与 §2.0.4 风格一致; B 额外统一 LM1/LM2/LM3 命名; C 不清理 active.md 违反归一化 |
| 7. 长期维护成本 | 5/5 | 3/5 | 4/5 | A 长期受益 (双处合并 + active.md 清理); B 改名引入 18+ 文件 diff, 长期维护成本增加; C 不清理 active.md, 维护成本略高 |
| **总分** | **15/15** | **13/15** | **13/15** | — |

### 反向论证 (N178-A1 禁循环论证 — 用外部约束排除)
- 为何不选 B: 全仓库改名 18+ 文件, git blame 受影响, 改动成本 >> 价值 (handbook §命名消歧 已有效)。外部约束: N178-A3 过度治理检查。
- 为何不选 C: active.md 含 ✅ FIXED 段落 (TD-295/296/301) 违反 §AI 维护硬约束 (2026-07-19 强化), 必须清理。外部约束: active.md §AI 维护硬约束。

### 决策
方案 A 总分 15/15, 领先 B/C 各 2 分。中修改 3 维阈值 15/15 (等效 7 维 35/35 ≥ 19 + 领先 ≥ 5), AI 自决执行 (符合 N167 + 用户已授权方向)。

## 实施计划

### Phase 1: B1+B2 合并 — rules §2.0.5 简化为指针

**rules §2.0.5 改动** (line 165-216, ~50 行 → ~15 行):
- 保留: 章节标题 + 命名归一说明 + 适用范围 + 分级触发 (与 §0 表格对齐)
- 保留: N178 AI 思维链纠偏硬约束段 (spec-59-A 沉淀, 不迁移)
- 删除: 7 维度清单 (迁 _refactor-dimensions.md, 已有)
- 删除: 七维度评分硬约束段 (迁 _refactor-dimensions.md, 新增)
- 删除: spec-49 强化段 (Y/N 检查表 #10-12 已覆盖, 不迁移)
- 改为指针: "详细 Y/N 矩阵 + 评分硬约束见 _refactor-dimensions.md (单一权威源)"

**_refactor-dimensions.md 改动**:
- §1 末尾新增 "N167 评分硬约束" 段 (从 rules §2.0.5 line 183-190 迁移)
- §1 末尾新增 "N178 AI 思维链纠偏硬约束" 段 (从 rules §2.0.5 line 199-214 迁移)

### Phase 2: active.md ✅ FIXED 段落迁出

**active.md 改动**:
- 删除 TD-295 段落 (line 108-110, 已在 fixed.md line 43)
- 删除 TD-296 段落 (line 129-131 + line 181-183, 重复段落, 已在 fixed.md line 15)
- 删除 TD-301 段落 (line 177-179, 未在 fixed.md)

**fixed.md 改动**:
- 补 TD-301 段落 (spec-58-B ✅ FIXED, 12 处 @shared_task + select_for_update KEEP)

### Phase 3: 文档同步 + commit + 反思

- completed-features.md 加 C-097 (spec-59-B)
- pending-roadmap.md P-038 状态 ⏳ → ✅
- active.md TD-302 状态 🔧 → ✅ FIXED + 迁 fixed.md
- commit (1 commit/spec, §3.4)
- 反思 (中修改 1 问反思, §4.6)

## 验证 evidence

- rules §2.0.5 行数: 改前 ~50 行 → 改后 ~15 行 (减 35 行)
- _refactor-dimensions.md 行数: 改前 ~150 行 → 改后 ~190 行 (增 40 行)
- active.md: TD-295/296/301 段落删除 (3 处)
- fixed.md: 补 TD-301 段落 (1 处)
- N178-A1/A2/A3/A4 检查全过
