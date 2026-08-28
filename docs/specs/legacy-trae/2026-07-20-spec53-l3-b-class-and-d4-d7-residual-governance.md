---
spec_id: spec-53
title: L3-4 B-class inclusion + d4/d7 residual governance
status: ✅ done
created: 2026-07-20
last_updated: 2026-07-20
related: spec-46 (d4 evidence/ downgrade), spec-50 (d7 b_minus_a fix), spec-49 (L3-4 hardstop)
n167_score: 34/35 (7 dimensions, large modification)
---

# Spec-53: L3-4 终止条件增强 (纳入 [B] 类) + d4/d7 残留进一步治理

> **来源**: spec-52 commit (`-`) 后用户反馈 "l3 怎么 a 类就停止了, 是不是得加个 b 类也一起好点? 或者再增加剩下的评估方向?"
> **目标**: (1) L3-4 终止条件纳入 [B] 类评估 + "已接受" 复查机制; (2) d4_path_drift 36 条 evidence/ 进一步治理 (P2 噪音消除); (3) d7 a_minus_c 13 条进一步治理 (P2 噪音消除)

## 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | N167 7 维度评分 + d4/d7 治理方案设计 | ✅ | 2026-07-20 | - | 34/35 自决; 3 治理方案选定 |
| Phase 2 | d4_path_drift: evidence/ 跳过 frontmatter 检查 | ✅ | 2026-07-20 | - | d4 P2 36→0 |
| Phase 3 | d7_index_consistency: a_minus_c_whitelist 实施 | ✅ | 2026-07-20 | - | d7 P2 13→0 |
| Phase 4 | L3-4 终止条件增强 (纳入 [B] + 已接受复查) | ✅ | 2026-07-20 | - | rules §3.7 + yn-matrices _workflow.md 更新 |
| Phase 5 | doc_health 验证 + 全量回归 + commit | ✅ | 2026-07-20 | - | P2 49→0; 55 tests PASS |

## §1 Background

### 1.1 来源

- spec-52 commit 后, L3-1 全量扫描报告 "无新 [A], L3-4 终止"
- 用户反馈: "l3 怎么 a 类就停止了, 是不是得加个 b 类也一起好点? 或者再增加剩下的评估方向?"
- 用户意图: L3 终止前应评估 [B] 类 + "已接受" 残留是否真的合理

### 1.2 现状

- doc_health_check 报 P2=49:
  - d4_path_drift P2: 36 (全在 evidence/, spec-46 已降级接受)
  - d7_index_consistency P2: 13 (a_minus_c, L1-小/中 已接受)
- L3-4 终止条件 ① "连续 2 轮无新增 [A] 类" 过早触发, 未评估 [B] + 已接受残留

### 1.3 根因

1. **d4 evidence/ 残留**: spec-46 把 evidence/ severity 从 P0 降到 P2, 但仍检查 frontmatter related_files (视为 contract)。实际上 evidence/ related_files 是"历史记录" (记录当时改了什么), 不是"当前 contract" (当前应存在)。后续重构后路径漂移是预期行为, 不应报警。
2. **d7 a_minus_c 残留**: §6.2 规定 L1-小/中 不需 yn-matrices, 但 d7 检查器仍对 L1-小/中 N## 报 a_minus_c P2。检查器无 level 概念, 对所有 Active N## 一视同仁。
3. **L3-4 终止条件**: 当前只看 [A] 无新增, 不评估 [B] 是否有明确修复方向 + 何时修, 也不复查"已接受" [B]/[C] 类是否仍合理。

## §2 N167 7 维度评分 (大修改)

### 2.1 方案 A (d4 evidence 跳过 + d7 whitelist + L3-4 增强) ✅

| 维度 | 分数 | 理由 |
|------|------|------|
| 1. 架构长远性 | 5/5 | 3 个治理都是长远解: evidence/ 历史快照不应阻塞 + L1-小/中 whitelist 集中管理 + L3-4 [B] 评估闭环 |
| 2. 全局归一化 | 5/5 | 集中管理: thresholds.yaml (d4 skip + d7 whitelist) + rules §3.7 (L3-4) + yn-matrices _workflow.md |
| 3. 新旧兼容 | 5/5 | 单人项目, 一次性切换, 无过渡逻辑 |
| 4. 现有业务完善 | 5/5 | 补齐 L3-4 [B] 类评估缺失 + "已接受" 复查机制 (用户反馈点) |
| 5. 性能资源优化 | 4/5 | P2 49→0 (或大幅减少), doc_health_check 飞轮读侧解锁; d4 evidence/ 跳过减少 63 文件扫描 |
| 6. 安全合规 | 5/5 | 不涉及权限/审计 (⑤ 理由: 纯文档治理, 不影响代码权限; ⑥ 理由: 不涉及敏感数据) |
| 7. 长期维护成本 | 5/5 | 一次性修复, 配套测试 + 文档; whitelist 需维护但成本低 (新 L1-小/中 N## 加一行) |
| **总分** | **34/35** | ≥ 19/21 阈值, AI 自决 |

### 2.2 反向论证 (为何不选 B/C/D)

- **方案 B (保留 P2 但加白名单注释)**: 25/35
  - 维度 1: 3/5 — 不解决根因, evidence/ 仍报 P2
  - 维度 4: 3/5 — 不补齐 L3-4 [B] 评估
  - 维度 7: 3/5 — 白名单注释需手动维护, 易遗漏
  - 不选理由: 治标不治本, 不解决用户反馈

- **方案 C (d4/d7 降级 P3)**: 15/35
  - 维度 1: 2/5 — P3 不存在 (severity 只支持 P0/P1/P2), 需改 report_schema.py
  - 维度 2: 2/5 — 改 schema 影响所有检查器
  - 不选理由: 需改 report_schema, 改动大且不必要

- **方案 D (只做 L3-4 增强, 不治理 d4/d7)**: 20/35
  - 维度 4: 3/5 — 只补齐 [B] 评估, 不解决"已接受"残留噪音
  - 维度 5: 2/5 — P2 49 不变, 飞轮读侧仍阻塞
  - 不选理由: 不解决用户反馈的"剩余评估方向"

### 2.3 硬场景 ③ 业务语义判定

- 影响数据保留/业务流程? **N** (evidence/ 历史快照保留, 只是不再检查路径; whitelist 集中管理 L1-小/中; L3-4 增强评估流程) → 可自决

## §3 实施

### 3.1 Phase 1: 设计 (已完成)

- d4: evidence/ 跳过 frontmatter related_files 检查 (修订 spec-46 决策: evidence/ related_files 是历史记录, 不是 contract)
- d7: thresholds.yaml 加 `a_minus_c_whitelist`, 列 13 个 L1-小/中 N##, 检查器跳过
- L3-4: "连续 2 轮无新增 [A] 类" 改为 "连续 2 轮无新增 [A]+[B] 类 + 已接受 [B]/[C] 类每 5 spec 复查"

### 3.2 Phase 2: d4_path_drift evidence/ 跳过

**修改 d4_path_drift.py**: 加 `skip_evidence_frontmatter` 配置 (默认 true)

```python
# Spec-53: evidence/ related_files is historical record, not contract.
# Skip frontmatter check for evidence/ files (revises spec-46 decision).
skip_evidence = thresholds.get("skip_evidence_frontmatter", True)
# ...
if rel.startswith(".ai-memory/evidence/") and skip_evidence:
    # Skip frontmatter check; evidence/ related_files is historical
    pass
else:
    for path_str in _extract_frontmatter_paths(content):
        # ... existing check
```

**修改 thresholds.yaml**: d4_path_drift 加 `skip_evidence_frontmatter: true`

### 3.3 Phase 3: d7 a_minus_c_whitelist

**修改 thresholds.yaml**: d7_index_consistency 加 `a_minus_c_whitelist`

```yaml
d7_index_consistency:
  a_minus_b_severity: "P1"
  b_minus_a_severity: "P2"
  a_minus_c_severity: "P2"
  # Spec-53: L1-小/中 N## don't require yn-matrices (§6.2). Whitelist to
  # avoid false positive a_minus_c P2 for these N##.
  a_minus_c_whitelist:
    - N121
    - N123
    - N132
    - N133
    - N136
    - N137
    - N139
    - N144
    - N145
    - N149
    - N158
    - N159
    - N176
```

**修改 d7_index_consistency.py**: 读 whitelist 跳过

```python
whitelist = set(thresholds.get("a_minus_c_whitelist", []))
a_minus_c = a - c - whitelist
```

### 3.4 Phase 4: L3-4 终止条件增强

**修改 project_rules.md §3.7 L3-4**:
- "连续 2 轮无新增 [A] 类" → "连续 2 轮无新增 [A]+[B] 类"
- 加 "已接受 [B]/[C] 类每 5 spec 复查一次" (防"已接受"永久化)

**修改 yn-matrices/_workflow.md §㉝ N166**: 同步 L3-4 增强

### 3.5 Phase 5: 验证

- doc_health_check: P2 49→0 (或大幅减少)
- 53 doc_health tests PASS + 新增 d4/d7 跳过测试
- 4 sync 工具 PASS

## §4 风险

- **低**: d4 evidence/ 跳过 — 失去 evidence/ 路径漂移检测, 但 evidence/ 是历史快照不需检测
- **低**: d7 whitelist — 需维护 (新 L1-小/中 N## 加白名单), 但成本低
- **低**: L3-4 增强 — 循环更彻底, 但可能延长循环时间 (用户已授权 AI 自决)

## §5 飞轮效果

- P2 49→0 (d4 36 + d7 13 全消除)
- doc_health_check 飞轮读侧完全解锁
- L3 循环更彻底 (纳入 [B] + 已接受复查)

## §6 沉淀

- 用户反馈 "l3 怎么 a 类就停止了, 是不是得加个 b 类也一起好点? 或者再增加剩下的评估方向?" 沉淀到:
  - `project_rules.md §3.7 L3-4` (纳入 [B] + 已接受复查)
  - `yn-matrices/_workflow.md §㉝ N166` (L3-4 增强)
  - 本 spec 文档
