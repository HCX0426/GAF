---
maintainer: manual
source: GAF/.ai-memory/evidence/active/2026-08-18-s34-agents-views-split/
load_when: [evidence, 3-step-evidence, s34, views-split]
priority: high
symptom: [验证结果, 测试全绿, ruff 通过]
solution: 命令级验证记录
related_files:
  - backend/agents/views.py
  - backend/agents/view_sets/
created_by: AI
last_updated: 2026-08-18
---
## Verification（验证）

$ D:\code\environment\conda\envs\gaf\python.exe manage.py check
预期：System check identified no issues (0 silenced) — 实际通过 ✓

$ D:\code\environment\conda\envs\gaf\python.exe -m ruff check backend/agents/views.py backend/agents/view_sets/
预期：All checks passed!（仅 1 个原文件遗留 SIM102 collapsible-if 非本次引入）— 实际通过 ✓

$ D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/agents/ -q --tb=short
预期：40 passed — 实际 40 passed ✓

$ D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/agents/tests/test_device_api.py backend/agents/tests/test_token_api.py backend/agents/tests/test_agent_core.py -q --tb=short
预期：15 passed — 实际 15 passed ✓

$ python -c "import agents.views; missing=[n for n in v.__all__ if not hasattr(v,n)]"
预期：import OK, all in __all__: True [] — 实际通过 ✓

$ python -c "import monitors.views; import agents.agent_runtime; import agents.urls"
预期：3 个引用方模块导入无 ImportError — 实际通过 ✓