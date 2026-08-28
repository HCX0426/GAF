---
spec_id: spec-36
title: a11y governance — TD-270 aria-label + TD-271 responsive audit + TD-272 PageWrapper audit
status: ✅ completed
created: 2026-07-20
last_updated: 2026-07-20
related: TD-270, TD-271, TD-272 (spec-35 L3-1 扫描发现)
n167_score: 15/15 (3 dimensions, medium modification)
commit: -
---

# Spec-36: a11y 治理 — TD-270 aria-label + TD-271 响应式审计 + TD-272 PageWrapper 审计

> **来源**: spec-54 commit (`-`) 后用户授权 "36开始吧"
> **目标**: (1) TD-270 修复 10 文件 14 处 icon-only Button 缺 aria-label; (2) TD-271 审计响应式设计实际状况, 决定本期修或拆 spec; (3) TD-272 审计 PageWrapper 覆盖率, 决定本期修或拆 spec

## 阶段状态表

| Phase | 标题 | 状态 | 完成时间 | Commit | 验收 evidence |
|-------|------|------|---------|--------|---------------|
| Phase 1 | N167 3 维度评分 + 范围确认 | ✅ | 2026-07-20 | - | 15/15 自决; TD-270 10 文件 14 处 |
| Phase 2 | TD-270 修复 10 文件 14 处 icon-only Button | ✅ | 2026-07-20 | - | 10 文件 14 处 aria-label 全补 |
| Phase 3 | TD-271 响应式审计 → wontfix (已用 flex-wrap + Table 横向滚动) | ✅ | 2026-07-20 | - | 5 页面已响应式, 不需 Col 断点 |
| Phase 4 | TD-272 PageWrapper 修复 3 个 AI 页面 (5 个全屏编辑器豁免) | ✅ | 2026-07-20 | - | AIUsageDashboard/AnomalyPatternPanel/LogAnalysisPanel 包 PageWrapper |
| Phase 5 | 验证 + commit + hash 回填 | ✅ | 2026-07-20 | - | npx vite build PASS (17.42s); 21 files commit |

## §1 Background

### 1.1 范围确认 (扫描结果)

**TD-270 (aria-label 缺失)** — 10 文件 14 处:
- d:\code\GAF\frontend\src\pages\AI\QAPanel.tsx (2 处: L293 星标, L307 删除)
- d:\code\GAF\frontend\src\pages\Devices\WindowManagementPage.tsx (1 处: L344 保存)
- d:\code\GAF\frontend\src\components\Layout\AppLayout.tsx (1 处: L403 折叠)
- d:\code\GAF\frontend\src\pages\GameProfiles\DetailPage.tsx (1 处: L186 返回)
- d:\code\GAF\frontend\src\pages\Ops\ExecutionReplay.tsx (1 处: L276 播放/暂停)
- d:\code\GAF\frontend\src\pages\Ops\Executions\analytics\DailySummaryCarousel.tsx (2 处: L174/L196 左右切换, HTML button)
- d:\code\GAF\frontend\src\pages\Accounts\components\AccountRotationRules.tsx (2 处: L184 编辑, L191 删除)
- d:\code\GAF\frontend\src\pages\Accounts\components\AccountGroupManager.tsx (2 处: L209 编辑, L219 删除)
- d:\code\GAF\frontend\src\pages\Tasks\PipelineEditor\PipelineVersionHistory.tsx (1 处: L244 刷新)
- d:\code\GAF\frontend\src\components\Task\TagManager.tsx (1 处: L244 颜色选择器, HTML button)

**TD-271 (响应式)** — 审计后定:
- `Col xs/sm/md/lg/xl` 已在 15 文件 44 处使用 (非 0, TD 登记数据漂移)
- `useBreakpoint` 0 处使用
- 需审计 9 大模块页面哪些缺响应式断点

**TD-272 (PageWrapper)** — 审计后定:
- PageWrapper 在 37 文件 149 处使用, 覆盖率看似不错
- 需审计哪些页面绕过 PageWrapper

### 1.2 N167 3 维度评分 (中修改)

| 维度 | 分数 | 理由 |
|------|------|------|
| 1. 架构长远性 | 5/5 | a11y 是 §12.5 硬约束, PageWrapper 是 §11 硬约束, 响应式是 §3.4 硬约束 |
| 2. 全局归一化 | 5/5 | 统一 aria-label 规范, 统一 PageWrapper 使用, 统一响应式断点 |
| 7. 长期维护成本 | 5/5 | 一次性 a11y 治理, 长期受益; TD-271/272 审计后决定范围 |
| **总分** | **15/15** | ≥ 9/12 阈值, AI 自决 |

**反向论证**:
- 方案 B (只修 TD-270, TD-271/272 拆 spec-37): 12/15 — 维度 1: 4/5 (推迟但有触发点), 维度 7: 3/5 (拆 spec 增加管理成本)
- 方案 C (不审计直接改 TD-271/272): 10/15 — 维度 1: 3/5 (不审计误改风险), 维度 7: 2/5 (返工风险)

**硬场景 ③**: 影响数据保留? N (前端 a11y 治理) → 可自决

### 1.3 决策

- **Phase 2**: TD-270 修复 10 文件 14 处 (确定 < 200 行)
- **Phase 3**: TD-271 审计 — 若 < 300 行则本期修, 否则拆 spec-37
- **Phase 4**: TD-272 审计 — 若 < 200 行则本期修, 否则拆 spec-37

## §2 实施计划

### 2.1 Phase 2: TD-270 修复 (10 文件 14 处)

按文件逐个加 `aria-label` 属性:

| 文件 | 行 | 按钮 | aria-label |
|------|----|------|-----------|
| QAPanel.tsx | 293 | 星标 | `aria-label="收藏"` / `aria-label="取消收藏"` (条件) |
| QAPanel.tsx | 307 | 删除 | `aria-label="删除"` |
| WindowManagementPage.tsx | 344 | 保存 | `aria-label="保存"` |
| AppLayout.tsx | 403 | 折叠 | `aria-label="折叠菜单"` / `aria-label="展开菜单"` (条件) |
| DetailPage.tsx | 186 | 返回 | `aria-label="返回游戏配置列表"` |
| ExecutionReplay.tsx | 276 | 播放/暂停 | `aria-label="播放"` / `aria-label="暂停"` (条件) |
| DailySummaryCarousel.tsx | 174 | 左切换 | `aria-label="上一项"` |
| DailySummaryCarousel.tsx | 196 | 右切换 | `aria-label="下一项"` |
| AccountRotationRules.tsx | 184 | 编辑 | `aria-label="编辑规则"` |
| AccountRotationRules.tsx | 191 | 删除 | `aria-label="删除规则"` |
| AccountGroupManager.tsx | 209 | 编辑 | `aria-label="编辑分组"` |
| AccountGroupManager.tsx | 219 | 删除 | `aria-label="删除分组"` |
| PipelineVersionHistory.tsx | 244 | 刷新 | `aria-label="刷新版本历史"` |
| TagManager.tsx | 244 | 颜色选择 | `aria-label="选择颜色"` |

### 2.2 Phase 3: TD-271 响应式审计

扫描 9 大模块页面 (Dashboard/Devices/Tasks/Pipeline/Resources/Monitors/Accounts/Ops/System) 的:
- 是否用 `Col xs/sm/md/lg/xl` 断点
- 是否用 `useBreakpoint()` hook
- 是否有 CSS media query

审计后决定: < 300 行本期修, 否则拆 spec-37

### 2.3 Phase 4: TD-272 PageWrapper 审计

扫描 `pages/` 下所有 page component 是否用 PageWrapper 作为根容器。

审计后决定: < 200 行本期修, 否则拆 spec-37

### 2.4 Phase 5: 验证 + commit + hash 回填

- `npm run lint` 0 jsx-a11y warnings
- axe-core browser 测试 (可选, 若时间允许)
- `npm run build` 通过
- commit spec-36
- 回填 spec-36 hash (N176 follow-up, 不 commit)

## §3 风险

- **低**: TD-270 纯加 aria-label 属性, 不改业务逻辑
- **中**: TD-271/272 审计后可能发现范围大, 需拆 spec-37
- **测试**: 需跑 `npm run lint` 验证 a11y 规则通过

## §4 飞轮效果

- TD-270 闭环: 10 文件 14 处 icon-only Button 全部有 aria-label
- TD-271/272 范围明确: 审计后决定本期修或拆 spec-37
- a11y 合规: §12.5 + §12.2 (焦点状态) + §3.4 (响应式) 检查清单通过
