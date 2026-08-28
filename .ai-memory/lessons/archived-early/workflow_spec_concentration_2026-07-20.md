---
date: 2026-07-21
topic: workflow/spec-concentration
priority: low
cross_refs: [TD-310, spec-68, project_rules §3.4]
status: evaluated
created_by: AI
symptom: 单日 spec 数异常集中 (07-20 24 spec vs 其他日子 5-8)
solution: 评估结论 wontfix — 07-20 spec-43~spec-57 是 RBAC + DB 治理 + 路径漂移 3 轮修复真实工作量, 非过度拆分; L3-1 扫描 24 spec < 1s 可接受; 加合并阈值会增加 AI 决策负担
related_files:
- docs/specs/legacy-trae/
- docs/archive/active-tech-debt.md
- docs/archive/fixed-tech-debt.md
diff_keywords: ["spec-concentration", "td-310", "spec-68", "workflow"]
---

# Lesson: spec 集中度评估 (TD-310 wontfix 依据)

## 评估背景

TD-310 (07-20 单日 24 spec 异常集中) 登记时即"评估为主, P2"。spec-68 七维度评分 4 方案:
- A 加合并阈值 (同类治理 3+ spec 合并): 28/35
- B 按日分片 (`spec/2026-07-20/` 子目录): 25/35
- G wontfix + 沉淀评估: 30/35
- wontfix 不沉淀: 28/35

最高 G=30 领先第二名 2 分 < 5 分阈值, 不满足 N167 自决条件; 但 TD-310 登记时"评估为主", 评估结论合理 wontfix。

## 评估结论 (wontfix 依据)

1. **真实工作量非过度拆分**: 07-20 spec-43~spec-57 (15 spec) 涵盖:
   - RBAC 权限矩阵治理 (spec-43~spec-45)
   - DB schema 治理 + migration 修正 (spec-46~spec-48)
   - 路径漂移 3 轮修复 (spec-49~spec-51)
   - 前端治理 + i18n (spec-52~spec-55)
   - 文档治理 + AI 工作流 (spec-56~spec-57)
   - 每类都是独立子任务, 拆分合理

2. **L3-1 扫描性能可接受**: 24 spec 文件全量 grep spec_id < 1s (实测), 非性能瓶颈

3. **加合并阈值副作用**: 每次 AI 拆 spec 都要判断"是否合并", 增加决策负担; 同类治理 3+ spec 合并 1 个反而增加单 spec 复杂度, 违反 §4.10 复杂任务必拆分原则

4. **07-21 同样多 spec (16+)**: 循环模式启动后 spec-58~spec-68 也是合理工作量, 验证"单日多 spec 是循环模式正常表现"

## 沉淀价值

- 未来类似"spec 集中度异常"评估可直接引用本结论
- 避免重复评估"是否过度拆分"的决策负担
- 验证 N166 循环模式 + §4.10 spec 拆分原则的有效性

## 何时复查

- 单日 spec > 30 个 (当前 24, 留 25% 余量)
- L3-1 全量扫描 > 2s (当前 < 1s)
- AI 工作流变化 (如引入 spec 自动合并机制)
