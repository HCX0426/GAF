# solution.md — P3 执行方案与 Y/N 检查 (commit b34d183 + 9fd0085)

## 变更
- `git mv agent/ worker/` 277 renames (R100, 内容字节不变)
- 875+ 行路径改写: bulk-replace (agent/src, agent.tests, agent.platforms, agent/debug, python agent/) + requirements/launcher/docs 定点
- 6 个 root-cause 定点: spawn/kill matcher; background_key_input 顶层 import 修复; gaf_daemon/sync_error_codes_i18n/tasks_rag/health/views/schema hook 的 WORKER_* 常量
- 2 个测试修复 (log_rotation logger level)

## P4 选中的 Y/N 检查 (select_reflection_checks.py --diff 9fd0085 → N166/N167/N117/N124/N112/N128)
来源脚本指向 `_cross-layer-sync.md` 不存在 → N112/N128 检查按 _workflow-commit 语义手动执行 (脚本目标文件名过期, 登记属文档债, 不阻塞本轮)。

### _refactor-dimensions.md 检查表
| # | 检查项 | Y/N | 证据 |
|:-:|--------|:---:|------|
| 1 | 7 维度评估 (weight: refactor → 重点 1,7; 标准 2,4; 豁免 3,5,6) | Y | carrier n167: 1=9/7=8/2=9/4=8/3=8/5=5/6=8, total 55 ≥19 领先 15 |
| 2 | 同根因扫描 (跨层引用) | Y | 三轮批量扫 175+ 文件 + 残留扫描清零 (grep 无 agent/(src|debug|tests|__main__) in scripts) |
| 3 | 无 deprecated/过渡注释 | Y | R100 纯改名, 无旧名保留 |
| 4 | 引用资源验证 | Y | related_files→worker/requirements.txt 存在; path-consistency hook PASS |
| 5 | 同根因扫描其他文件 | Y | agent/requirements.txt 全仓 7 活文件同步 (tech-stack/version-compat/deployment-design/procedure/env-hardrules/setup-dev-env/N187) |
| 6 | 文档同步 | Y | spec P3 ✅ + carrier decision_log 2 行 + 5 文档 |
| 7 | 性能 | N/A→3 | 纯改名无逻辑变更 |
| 8 | 安全 | N/A→3 | 无鉴权行为变更 |
| 9 | 测试 | Y | worker 2278P/0F/3S + backend 490P + makemigrations --check clean |
| 10 | ⑤⑥ 理由 | Y | carrier n167 附理由 |
| 11 | 反向论证 | Y | carrier P1 含 (计划批准后 P3 为执行段) |
| 12 | 硬场景③ | Y | 影响数据保留/业务流程? N → 自决 |

### N112 (跨层 sync, 后端→前端契约) — Y
改名仅限进程目录/符号, worker 全套 + backend 切片绿; api-contract 相关测试无漂移; 前端类型未动 (P6)。

### N128 (诚实状态) — Y
无新功能声称; 全部验证真实执行 (pytest 输出、makemigrations --check)。

### N117 (脚本并发) — N/A→Y
批量替换脚本均串行单次执行, 无并发复用点。

### N124 (skill 删除/重命名同步) — Y
本 spec 未删 skill; gaf-orchestrator 决策树仍有效。

## 反思 ⑤ evidence commit
本 evidence 目录随本次提交 (<evidence-commit-hash>)。

## 工具陷阱教训 (N174 式)
Edit 工具对多行缩进代码丢失前导空格 (2 次: test_ws_rpc.py / check_schema_unification.py) → 多行 edit 后必 py_compile/ruff 验证。同类风险归入 failure-modes 候选, 触发 ≥3 次再升 N## (gate-1)。