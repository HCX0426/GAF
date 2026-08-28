---
summary: 活跃技术债务清单 — 🔧 待修/待办/待决 和 🚧 进行中 条目 (完整详情)
applies_to: [project]
last_updated: "2026-08-29 (TD-415 登记: log_rotation 跨天轮转 _stream=None)"
---

# Active Tech Debts (待修 / 进行中)

> Only active tech debts listed here. Closed/WONTFIX entries moved to `fixed.md` or `wontfix.md`.
>
> 本文件只包含真正活跃的技术债务（🔧 待修/待办/待决 和 🚧 进行中）。
> 已关闭条目（✅ FIXED / ❌ WONTFIX / ❌ INVALIDATED / ❌ EVALUATED）已迁移到 `fixed.md` 或 `wontfix.md`。
>
> **状态**: ✅ 全部闭环（TD-412/413/414 已于 2026-08-28 迁出 fixed.md，active 为空）

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

## TD-415: DateRotatingFileHandler 跨天轮转偶发 _stream=None (🔧)

- **状态**: 🔧 (登记 2026-08-29, 本次 spec 范围外检出)
- **优先级**: P3
- **登记时间**: 2026-08-29
- **来源**: spec 2026-08-29-services-management-monitor 实测 daemon status 时发现
- **症状**: `gaf_daemon.py status --json` / daemon 运行时 `log_rotation.py:139 emit → AttributeError: 'NoneType' object has no attribute 'write'`
  反复打印 Logging error; stdout 正常但文件 handler 失效 (跨天轮转后 `_stream` 为 None 未重建)
- **根因**: `DateRotatingFileHandler._rotate_if_needed` 在日期变化时 close 旧流后, 若 `_open_today()` 之前某异常路径
  或并发 (多进程同 handler) 导致 `_stream` 保持 None; 跨午夜后首条日志 emit 即崩 (handleError 吞掉, 日志持续丢失)
- **影响**: daemon/agent 跨天首条日志丢失 + 每次 status 调用刷 Logging error traceback; 文件句柄泄漏风险
- **修复方案**: `emit` 前对 None 自愈: `if self._stream is None: self._open_today()`; 并用 `single-file lock` 防止多进程并发写
- **验证标准**: ① 设置系统日期跨天 (或 mock datetime) 触发 rotate; ② 首条 emit 不再 AttributeError; ③ status/daemon 连续 3 次调用无 Logging error; ④ 当天日志文件持续增长且无 .gz 缺失
- **何时修**: 下一轮 L3 循环 (agent 日志可靠性, 涉及 agent+scripts 两处 import 同一 handler)
- **三维根因评估**: 代码 (emit 无 None 守卫) + 工作流 (跨天场景长期未测) + 规则 (无跨天轮转测试用例)
- **修复方案验证**: ✅ grep `log_rotation.py` emit/None/rotate 三处确认缺口; 复现命令 `python scripts/gaf_daemon.py status --json` → Logging error (2026-08-29 实测复现)

---






