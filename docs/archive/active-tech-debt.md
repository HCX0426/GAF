---
summary: 活跃技术债务清单 — 🔧 待修/待办/待决 和 🚧 进行中 条目 (完整详情)
applies_to: [project]
last_updated: "2026-08-31 (TD-423 登记: LLM 多 provider + AI 页签分组)"
---

# Active Tech Debts (待修 / 进行中)

> Only active tech debts listed here. Closed/WONTFIX entries moved to `fixed.md` or `wontfix.md`.
>
> 本文件只包含真正活跃的技术债务（🔧 待修/待办/待决 和 🚧 进行中）。
> 已关闭条目（✅ FIXED / ❌ WONTFIX / ❌ INVALIDATED / ❌ EVALUATED）已迁移到 `fixed.md` 或 `wontfix.md`。
>
> **状态**: 🔧 1 项待修 (TD-423, 2026-08-31 登记; TD-415~422 已闭环)

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

## TD-423: LLM 多服务商 Provider 配置缺失 + AI 页签分组混乱 (🔧 待修)

- **状态**: 🔧 待修
- **优先级**: P1
- **登记时间**: 2026-08-31
- **来源**: 2026-08-31 用户评估诉求（"API Key 管理应移到 AI 页签 + 评估 AI 页签是否乱 + 对照开源 IDE 多服务商 key 加载"）— 评估完成, 结论登记
- **症状**: ① `settings.LLMConfig` 为**单条**模型, 前端 AiConfigPage 虽有 provider 预设 (openai/deepseek/qwen/ollama/custom) 但同一时间只能存一个 provider, 切换即覆盖 api_key — 无法多服务商并存; ② AI 页签 8 子页平铺 (assistant/qa/anomaly/log-analysis/skill-editor/skill-market/config/usage) 横跨 4 维度无分组, 侧边栏显"乱"; ③ `assistant`(LangGraph Agent) 与 `qa`(RAG QASession) 两个对话入口并存, 历史重叠
- **根因**: LLMConfig 早期按"单活配置"设计, 未随多 provider 需求演进; AI 侧边栏按功能演进平铺, 未做信息架构分组; 对话产品历史上有 Agent/QA 两条独立实现路径
- **影响**: 用户换服务商需重填 key; 无法"一处管理多 key + 按用途激活"（VS Code BYOK / Continue.dev 等开源标准做法）; AI 页签认知负担高
- **修复方案**: 对齐开源两级结构 (Provider[apiKey/baseUrl] → Model[], 集中管理 + 按用途激活 + 每 provider 连通测试): ① LLMConfig 升级为多行/多 provider（或新 LLMProvider 模型 + 迁移）; ② AI 侧边栏分 4 组 (对话/分析/Skill/配置运维); ③ assistant/qa 归一做 N151 架构评估（LangGraph Agent vs QASession 取舍）
- **验证标准**: 可同时配置 ≥2 个 provider 且互不覆盖; 各 provider 可独立 test 连通 + 一键切换激活; AI 侧边栏分组后导航清晰; (对话归一见独立评估)
- **何时修**: 用户确认推进时（2026-08-31 已确认"仅评估暂不动"）; 触发点 = 用户明确要落地 AI 多 provider 改造时
- **实施计划**: 2026-08-31 已产出学习型总纲 spec — `docs/specs/active/2026-08-31-ai-tab-agent-learning-spec.md`（Phase1 多 provider + Phase2 手写 LangGraph/MCP + Phase3 RAG rerank/Agent 评测，含 2026 年 JD 对标与框架选型评估）

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
