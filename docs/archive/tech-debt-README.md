---
summary: GAF 技术债务登记表 — 集中记录所有计划外技术债务 (TD-NNN)
applies_to: [backend, frontend, agent, project]
last_updated: 2026-08-30
---

# GAF 技术债务登记表 (Tech Debt Register)

> **目的**：集中记录所有"本轮计划外但必须处理"的技术债务。每轮实现计划完成后，AI 必须检查本目录并继续处理 tech debt（project_rules.md §4.8）。
>
> **维护规则**：
> - 任何任务中发现的"非本轮范围内"问题，必须登记一行（TD-NNN）
> - 修复后必须把状态改为 ✅ FIXED 并附 commit hash + evidence
> - 不允许"既不登记也不修复"的悬空状态
> - 每轮 plan 实现完成后，AI 必须扫描本目录，挑 1-2 个高优先级 debt 推进

## 目录结构

本登记表于 2026-07-10 从单文件 `tech-debt-register.md`（1350+ 行）拆分为目录结构：

| 文件 | 内容 | TD 数量 |
|:---|:---|:---:|
| [active-tech-debt.md](active-tech-debt.md) | 🔧 待修/待办/待决 和 🚧 进行中 条目（完整详情） | 0 |
| [fixed-tech-debt.md](fixed-tech-debt.md) | ✅ FIXED 条目（完整详情） | 155 |
| [wontfix-tech-debt.md](wontfix-tech-debt.md) | ❌ WONTFIX / ❌ INVALIDATED / ❌ EVALUATED 条目（完整详情） | 34 |
| **合计** | | **189** |

> **注**: 计数于 2026-08-09 同步: TD-330/TD-335/TD-336 ✅ FIXED 迁移到 fixed.md, active 3→0, fixed 240→243, total 275; active.md 已归档。前一同步: TD-345 ✅ FIXED 迁移到 fixed.md, fixed 239→240, total 274→275; TD-319 完成后由 sync_tech_debt_counts.py 自动维护。

> 原文件 `tech-debt-register.md` 已替换为重定向说明，实际内容迁移到本目录。

## 严重度定义

- **P0 (阻塞)**：核心功能不可用，必须立即修复（如 TD-003 截不到游戏画面）
- **P1 (重要)**：影响可靠性或开发效率，本轮或下轮修
- **P2 (中等)**：有 workaround，可推迟但要登记
- **P3 (轻微)**：代码异味，重构时顺手修

## 状态定义

- 🔧 **待修/待办/待决**：已登记但未开始
- 🚧 **进行中**：已开始但未完成
- ✅ **FIXED**：已修复，附 commit hash + evidence
- ❌ **WONTFIX**：评估后决定不修，附理由
- ❌ **INVALIDATED**：原始描述失效（基于错误判断），不再处理
- ❌ **EVALUATED**：评估后决定不修（如 squash 不可行），附评估结论

## 技术债务统计

本目录所有技术债务已处理完毕。详细的历史记录和解决方案请查阅对应文件：

*   **活跃债务** ([active-tech-debt.md](active-tech-debt.md)): 0 条 (🎉 全部解决)
*   **已修复债务** ([fixed-tech-debt.md](fixed-tech-debt.md)): 243 条
*   **WONTFIX/INVALIDATED/EVALUATED** ([wontfix-tech-debt.md](wontfix-tech-debt.md)): 32 条
*   **合计**: 275 条

> 新发现的技术债务请登记到 [active-tech-debt.md](active-tech-debt.md)。

## Review Checklist (每轮 plan 实现完成后必跑)

AI 在每轮 plan 实现完成后，必须执行以下步骤：

1. **扫描 [active-tech-debt.md](active-tech-debt.md)**：读取所有 🔧 待修/待办/待决 和 🚧 进行中 状态的条目
2. **挑 1-2 个高优先级 debt**：优先 P0 > P1 > P2 > P3
3. **创建子任务**：在本轮 plan 的工作目录或下一轮 plan 中创建子任务
4. **推进 debt**：实现修复或决策，更新对应文件状态
5. **commit**：附 commit hash 到对应文件条目；修复后从 active.md 迁移到 fixed.md（或 wontfix.md）

**禁止行为**：
- ❌ 跳过本检查直接进入下一轮 plan
- ❌ 把"修不了"的 debt 留在 🔧 状态超过 3 轮（要么修，要么标 ❌ WONTFIX 附理由）
- ❌ 登记新 debt 时不写"何时修"字段
