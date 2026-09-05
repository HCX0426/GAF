---
summary: 活跃技术债务清单 — 🔧 待修/待办/待决 和 🚧 进行中 条目 (完整详情)
applies_to: [project]
last_updated: "2026-09-05 (TD-425 登记: 链执行卡死无超时清理)"
---

# Active Tech Debts (待修 / 进行中)

> Only active tech debts listed here. Closed/WONTFIX entries moved to `fixed.md` or `wontfix.md`.
>
> 本文件只包含真正活跃的技术债务（🔧 待修/待办/待决 和 🚧 进行中）。
> 已关闭条目（✅ FIXED / ❌ WONTFIX / ❌ INVALIDATED / ❌ EVALUATED）已迁移到 `fixed.md` 或 `wontfix.md`。
>
> **状态**: 🔧 1 项待修 (TD-424, 2026-09-01 登记)

## TD 处理顺序 (2026-07-18 spec-26 强化)

> **来源**: 用户反馈 2026-07-18 — "要是有技术债务，为啥会延后，延后也是指在做完上一个类别接着做，而不是等我的指令"
> **硬约束**: 见 `project_rules.md §4.8` — "延后" = 做完上一个 spec/类别后立即接着做, **不是等用户指令**

**AI 自动接修规则**:
1. 当前 spec 全部 ✅ 后, AI **主动**按优先级 + 登记时间接修下一个 TD, 不等用户指令
2. 优先级排序: P1 > P2 > P3; 同优先级按登记时间 (先登记先修)
3. 批量合并: 若剩余 TD 均 P3 且合计 < 500 行, 合并 1 个 spec 批量处理
4. 单独 spec: 若单个 TD > 500 行或跨模块, 单独开 spec

**"何时修" 字段语义**:
- ✅ 合法写法: "spec-XX 完成后立即接修" / "下一 spec" / "L3 Round N 后接修" (明确触发点)
- ❌ 禁止写法: "后续 Phase" / "下次重构" / "待定" / "看情况" (模糊延后 = 等用户指令)

**完整待修 TD 清单见 tech-debt/README.md 总览表**

---

## TD-XXX: <title> (🔧 待修)

- **状态**: 🔧 待修
- **优先级**: P1/P2/P3
- **登记时间**: YYYY-MM-DD
- **来源**: <where this TD was discovered>
- **症状**: <observable symptom>
- **根因**: <root cause>
- **影响**: <impact on functionality/performance/etc>
- **修复方案**: <proposed fix>
- **验证标准**: <how to verify the fix>
- **何时修**: <when to fix>
-->

---

## TD-424: 对外 API Key 管理无鉴权消费点（僵尸 CRUD） (🔧 待修)

- **状态**: 🔧 待修
- **优先级**: P2
- **登记时间**: 2026-09-01
- **来源**: 2026-09-01 用户审查"系统 API Key 管理与 AI 模块是否冗余"——评估确认与 `LLMConfig` 用途不同（**不冗余**），但发现 `APIKey` 无生产消费点
- **症状**: `accounts.APIKey`（[models.py](backend/accounts/models.py#L248)）+ `/system/api-keys` 页面提供完整 CRUD（key_hash/权限/IP 白名单/调用计数/过期），但全仓无任何 middleware / authentication backend / 业务代码消费该密钥做鉴权
- **根因**: 早期规划"对外 API 开放"能力未完成，CRUD 先行、鉴权接入未落地
- **影响**: 用户可在界面创建 API key 但无法用其调用任何接口（功能形同虚设）；与 AI 模块 `LLMConfig.api_key` 概念混淆（两者都叫 API Key 但用途不同：对外密钥 vs LLM 服务商密钥）
- **修复方案**: 已实现 `accounts.APIKeyAuthentication`（[authentication.py](backend/accounts/authentication.py)）— sha256 key_hash 校验 + is_active + 过期 + IP 白名单 + call_count 递增，8 项测试通过；按"暂不对外开放"决策，**尚未接入任何公开端点**
- **验证标准**: 接入端点后，用创建的 API key 能调用受保护接口且 call_count 递增; 当前鉴权后端单测 8 项通过
- **何时修**: 对外 API 有开放需求时，把 `APIKeyAuthentication` 加入目标视图的 `authentication_classes`（2026-09-01 已实现功能代码）

---

> 2026-08-26 迁移记录：
> - TD-395/396/397/398/399 → fixed（spec-2026-08-26 闭环，commit - 等；TD-396 由 2026-08-26 连续 10 次执行全 success 终确）
> - TD-400 → fixed（loop rotation 实现 + 关闭，commit - / -）
> - TD-401 → fixed（18 vitest 用例，commit -）
> - TD-402 → fixed（链执行器可靠性 5 项，commit -）
> - TD-403 → fixed（伪失败确认：tasks 全量 215 passed --create-db 干净库，判定为并发 create-db 重建窗口假象）
> - TD-404 → fixed（前端 tsc 归零：NodePropertyPanel TS1117 重复键 + test TS6133 未用导入）
> - TD-405 → fixed（doc_health P1=0：docs-index.md 补 last_manual_edit）
> **Note**: TD 状态迁移 (✅ FIXED → fixed-tech-debt.md) 按 §4.5 执行。
> - TD-406 → fixed（策略页恢复流程摘要改为随配置动态拼接，commit -）
> - TD-407 → fixed（TaskExecutionSerializer 增 task_name/agent_hostname + 执行列表渲染名称，commit -）
> - TD-408 → fixed（backend ruff 79 条归零，commit -）
> - TD-409 → fixed（frontend eslint 165 条归零：compiler 规则降级 warn + 31 真实问题修复，commit -）
> - TD-410 → fixed（agent ruff 276 条归零，commit -）
> - TD-411 → fixed（frontend prettier 全仓 272 文件格式收敛，commit -）
> - TD-412 → fixed（N105 出清 + N201 行修复，check-cap 35 ≤ 35，2026-08-28）
> - TD-414 → fixed（N209/N210/N211 补 yn-matrices 条目，doc_health 0，2026-08-28）
> - TD-413 → fixed（SKILL.md 27.6KB→18.3KB 瘦身，9 处冗余外迁/压缩，2026-08-28）

---

> 2026-08-29 迁移记录:
> - TD-415 → fixed（log_rotation 跨天自愈 + 测试，见 fixed.md）
> - TD-416 → fixed（消息帧日志写入，commit 2fcff72，7+1 测试）
> - TD-417 → fixed（应用日志文件数据源收口，commit 2fcff72）
> - TD-418 → fixed（审计双入口收敛，commit d484c39/2fcff72）
> - TD-419 → fixed（服务管理 e2e + AI 调试文档，spec P4/P5）
> - TD-420 → fixed（MonitorRule.rule_kind 拆分，见 fixed.md）
> - TD-421 → fixed（通知链路打点 + chain-health，见 fixed.md）
