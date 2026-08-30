# solution.md — P5 执行细节与 Y/N (commit 323ef94)

## 策略
模块改名用 `git mv`(保历史);文本替换用 Python 字节级 read_text/write_text utf-8 newline 保持(PowerShell Get-Content/Set-Content 会损坏 CJK — P1/P2 多次教训)。逐 token 规则 + ZERO-flat 计数审计(本次 17 文件 24 规则全部 ≥1 命中,无漏网)。

## token 表 (17 files)
- worker_selector.py: agent_selector x1 / AgentSelector x5
- tasks.py: agent_selector x1 / AgentSelector x4
- test_worker_selector.py: agent_selector x1 / AgentSelector x20
- worker_runtime.py: 内部 0 自引用(grep 证实,无需替换)
- apps.py: `from . import` x2 + `start_heartbeat_loop()` x2
- crud.py: lazy import x1 + log msg x1
- views.py 注释, __main__.py x2 注释, health.py 注释
- hooks x2 (测试路径), lessons N186/N216/N191 related_files x3, docs x4 (符号/路径)

## 关键决策
1. G-9 AgentViewSet P1 已改名 → 本次不重做,spec 记录 "verified already landed"。
2. hooks check_schema_unification:121 / check_code_rules:224 引用 `test_agent_selector.py` 白名单路径 → 同步改名,否则提交后 hook 崩溃。
3. lessons 只改 related_files 路径(保证可加载),正文历史叙述保留(non-destructive 原则)。
4. health.py E402 预存 (sys.path guard 顺序) — 非 P5 引入,HEAD 基线 1=1 证实,不动。

## Y/N (select N166/N167/N117/N124/N112/N128)
- N167 7 维 (refactor 重点 1,7): dim1=9 (模块语义收口, 与 Worker 系列一致), dim4=7 (git revert 可逆, 无迁移), dim7=8 (类名×20+路径×3 一处收口; prose 叙事残余明确分派 P6). 总分 54, A vs B (保留旧名) 领先 ≥5, self-approved.
- N112 跨层: 懒加载链 (apps ready / crud / __main__) 全部验证, slice 987 绿 — Y。
- N128 诚实: 无新功能声称, 全部实测 — Y。
- N117/N124: 不适用 — A。
- N166: 无新增 L3-A — Y。

## 残余 (deferred, 明确归属)
- 架构文档 prose "选 Agent"/"agent 健康探针"/dispatch-flow 叙事 → naming-e + P6 文案 sweep
- check_code_rules/check_schema_unification 白名单已同步 (无残余)