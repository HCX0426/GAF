---
spec_id: spec-59-C
title: TD-303 工作流节奏调整 + 规则退役 + TD 登记上限
td_refs: [TD-303]
parent_spec: spec-59-A (元评估识别弱项)
created: 2026-07-21
status: ✅ completed
task_type: documentation
n167_score: 14/15 (3 维 1/2/7, AI 自决 A 调整版领先 B 2 分 < 5 阈值, 用户授权)
ai_self_decide: false (用户授权选定 A 调整版)
---

## 阶段状态表

| Phase | 任务 | 状态 | 完成时间 | Commit | 验收 evidence |
|:---:|---|:---:|:---:|:---:|---|
| 0 | N151 架构盘点 + N167 评分 + AskUserQuestion 选 A 调整版 | ✅ | 2026-07-21 | — | N167 14/15, 用户选 A 调整版 (4 处阈值同步 + hash 立即回填 + N177 修订 + 规则退役 + TD ≤ 3) |
| 1 | rules §3.4 N176 + §3.6 + §4.9 N177 + §4.11 N180 + L3-4 修订 + 规则退役段 | ✅ | 2026-07-21 | - | grep "连续 3 spec\|第 4 spec\|3 spec 完成" → 0 处; N181 + L3-1 TD ≤ 3 + §4.12 规则退役机制已就位 |
| 2 | 文档同步 + commit + 反思 | ✅ | 2026-07-21 | - | active.md TD-303 迁出 + fixed.md TD-303 闭环段 + completed-features C-098 + pending-roadmap P-039 ✅ + failure-modes.md N177-N181 索引补全 |

## 背景

spec-59-A 元评估识别 4 项工作流弱项 (C1/C3/C4) + 2 项根因 (D1/D2):

- **C1 3 spec 后停太松**: 累积上下文压力大 (本对话已压缩 1 次)
- **C3 文档同步过载**: 每 spec 同步 4-5 文档, hash 遗漏频发 (spec-58-B/59-A hash 在 spec-59-B 才回填)
- **C4 测试策略矛盾**: §4.9 全量回归 + N177 分级测试边界没说清 (N177 "第 4 spec" 与 "2 spec 后停" 永远矛盾)
- **D1 规则膨胀无退役**: N150-N180 已 31 条, 无定期退役机制
- **D2 TD 登记膨胀**: spec-55 L3-1 一次扫 20 个 [B] → 6 个 TD, active.md 又在膨胀

## N151 架构盘点

**现状清单**:
- §3.4 N176 hash 回填 (line 242-249): "下次 spec commit 时一并回填上一 spec hash"
- §3.6 spec-49/spec-52 放松 (line 309, 315): "连续 3 spec 完成后强制停下" + "L3-4 终止条件 (连续 3 spec)"
- §4.9 N177 (line 495): "循环模式下连续 ≥ 3 spec 仅跑相关 app 时, 第 4 spec 必跑一次全套回归"
- §4.11 N180 (line 531): "连续 3 spec 完成后强制停下时, 必跑元评估"
- 无规则退役机制
- L3-1 无 TD 登记上限

**反模式识别**:
1. **3 spec 阈值散落 4 处** → 改 2 spec 需同步 4 处, 易遗漏
2. **hash 回填靠下次 spec commit** → 模糊延迟, 实测常漏
3. **N177 "第 4 spec"** 与 "2 spec 后停" 矛盾
4. **规则无退役机制** → N## 累积执行疲劳
5. **L3-1 无登记上限** → active.md 膨胀

## N167 评分 (3 维 1/2/7, 中修改)

| 维度 | A 调整版 | B 温和 | C 最小 |
|------|----------|--------|--------|
| 1 架构长远性 | 5 (4 处阈值同步归一) | 4 (3 处归一) | 3 (只改阈值) |
| 2 全局归一化 | 5 (4 处归一 + 交叉引用) | 4 (3 处归一) | 2 (1 处) |
| 7 长期维护成本 | 4 (退役机制降累积) | 4 (退役机制) | 3 (无退役) |
| **总分** | **14** | **12** | **8** |

A 领先 B 2 分 < 5 阈值 → AskUserQuestion → 用户选 A 调整版

## N178-A1~A4 自检

- **A1 反向论证无循环论证**: A 方案把 4 处散落 "3 spec" 归一, 基于实测遗漏 (spec-59-B 漏改 §4.11), 非自我证明 ✅
- **A2 维度 4-7 必须给理由**: 维度 7 长期维护 4/5 理由 = 退役机制降低 N## 累积执行疲劳; 维度 4/5/6 N/A (文档治理无业务/性能/安全影响) ✅
- **A3 过度治理检查**: A 原方案合并 §4.9+§4.11 到 §3.6 会破坏段落独立性 → 调整为保留段落 + 加交叉引用 (不过度治理) ✅
- **A4 spec 范围限制**: TD-303 描述 C1/C3/C4/D1/D2 五项, A 调整版全覆盖 + N177 修订 (C4 一部分), scope deviation 0 ✅

## 修复方案 (A 调整版)

### Phase 1: 5 处规则修订

1. **§3.4 N176 hash 回填机制修订**:
   - 原: "下次 spec commit 时一并回填上一 spec hash"
   - 改: "commit 后立即 follow-up edit 回填 hash 到 spec 文件 (1 次 edit, 不 commit, 留到下次 spec commit 时带); 若本对话无下一 spec, follow-up edit 单独 commit"

2. **§3.6 spec-49/spec-52 放松修订**:
   - 原: "连续 3 spec 完成后强制停下" + "L3-4 终止条件 (连续 3 spec)"
   - 改: "连续 2 spec 完成后强制停下" + "L3-4 终止条件 (连续 2 spec)"
   - 同步: §3.6 line 309/315 + L3-4 终止条件段

3. **§4.9 N177 修订**:
   - 原: "循环模式下连续 ≥ 3 spec 仅跑相关 app 时, 第 4 spec 必跑一次全套回归"
   - 改: "循环模式下每 2 spec 后必跑一次全套回归 (与 L3-4 终止条件对齐)"
   - 加交叉引用: "见 §3.6 L3-4 终止条件"

4. **§4.11 N180 修订**:
   - 原: "连续 3 spec 完成后强制停下时, 必跑元评估"
   - 改: "连续 2 spec 完成后强制停下时, 必跑元评估"
   - 加交叉引用: "见 §3.6 L3-4 终止条件"

5. **新增规则退役机制段 (§6.3 或 §4.12)**:
   - 位置: §4.12 (规则退役机制 — N181, spec-59-C 新增)
   - 内容: N## 季度评估; 已融入 AI 习惯的可退役到 `archived-lessons.md`; 退役条件 (连续 5 spec 未触发反思该 N## / 已被新 N## 覆盖 / AI 默认行为已符合)
   - 退役 ≠ 删除: 迁到 archived-lessons.md 保留历史, failure-modes.md §Active → §Retired

6. **§3.7 L3-1 TD 登记上限**:
   - 新增: "L3-1 一次扫描登记 TD 数上限 ≤ 3 个 (防 active.md 膨胀); 超过 3 个的 [B] 类标 'L3-1 后续 round' 留下次扫描"

### Phase 2: 文档同步 + commit + 反思

- active.md: TD-303 段落迁出到 fixed.md
- fixed.md: 加 TD-303 闭环段 (N174 grep 验证)
- completed-features.md: 加 C-098
- pending-roadmap.md: P-039 ✅
- failure-modes.md: 加 N181 索引 (规则退役机制)
- yn-matrices.md: 若 N181 需 sub-file, 加索引 (按需)
- commit: `refactor(rules): spec-59-C TD-303 工作流节奏 + 规则退役 + TD 上限 (2 spec 强制停 + hash 立即回填 + N177 修订 + N181 退役机制 + L3-1 TD ≤ 3, N167 14/15 用户授权)`
- 反思: N179 中修改 1 问 + N178-A1~A4 检查

## 验证 evidence

- `grep "连续 3 spec" .trae/rules/project_rules.md` → 0 处 (全改 2 spec)
- `grep "第 4 spec" .trae/rules/project_rules.md` → 0 处 (N177 已修订)
- `grep "N181" .ai-memory/meta/failure-modes.md` → 1 处 (新增索引)
- `grep "L3-1 一次扫描登记 TD 数上限" .trae/rules/project_rules.md` → 1 处
- `grep "TD-303" docs/general/tech-debt/active.md` → 0 处 (已迁出)
- `grep "TD-303" docs/general/tech-debt/fixed.md` → 1 处 (闭环段)
