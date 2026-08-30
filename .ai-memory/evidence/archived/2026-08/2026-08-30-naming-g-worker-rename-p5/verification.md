# verification.md — P5 验收证据 (commit 323ef94)

## 提交
- `323ef94` refactor(worker): rename agent_runtime->worker_runtime and AgentSelector->WorkerSelector (naming-g P5 ; 20 files, 67+/66-, 治理 PASS)

## 变更
- G-8: git mv backend/workers/agent_runtime.py -> worker_runtime.py; apps.py heartbeat import x2, crud.py lazy import + log msg, views.py stale comment, worker/src/__main__.py x2 comments, scripts/services/health.py comment, lessons N186/N216 related_files, docs deployment-design.
- G-12: git mv backend/tasks/agent_selector.py -> worker_selector.py + tasks/tests/test_agent_selector.py -> test_worker_selector.py; class AgentSelector->WorkerSelector (module docstring, __main__ guard, 20 test instantiations); tasks.py import + comments x4; hooks check_schema_unification/check_code_rules test-path x2; lessons N191 related_files; docs data-flow x1 + dispatch-flow x5 + concurrency-design x10 (symbols/paths only).
- G-9: verified ALREADY done (crud.py:38 class WorkerViewSet + views re-export) — no work needed.

## 测试 / 检查
| 项 | 结果 |
|----|------|
| pytest backend tasks+workers | 255 passed / 37 deselected / 0 failed |
| pytest backend slice (protocol workers tasks device_bridge monitors tests gaf_ai.test_ws_rpc gaf_core) | 987 passed / 85 deselected / 0 failed |
| makemigrations --check --dry-run | No changes detected |
| rubric ruff (9 changed py + __main__.py) | 1 I001 auto-fixed; remaining 1 E402 = pre-existing (HEAD baseline flat 1=1, health.py:37 sys.path guard) |
| residual grep agent_selector/AgentSelector/agent_runtime. | backend / worker / scripts / frontend: 0 hits |

## 边界 (frozen / deferred 未触碰)
- 迁移历史、archived evidence/spec-contexts、analysis/concept-naming-normalization.md (计划源)、naming-g spec 目标表旧名 (历史标记)。
- prose 文案 "选 Agent"/"agent 健康探针" → naming-e / P6 sweep。