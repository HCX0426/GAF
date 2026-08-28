---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反思, 写教训]
priority: high
symptom: [kb:td396, agent掉线, backend冻结, GIL, RAG索引]
solution: Verification 记录 TD-396 验证命令与结果
related_files:
  - backend/gaf_ai/rag.py
  - backend/gaf_ai/tests/test_llm.py
created_by: AI
last_updated: 2026-08-26
---
## Verification（验证）

$ conda run -n gaf python -m pytest backend/gaf_ai/tests/test_llm.py -q --tb=short
$ conda run -n gaf python -m ruff check backend/gaf_ai/rag.py backend/gaf_ai/apps.py backend/gaf_ai/tasks_rag.py

预期：62 passed；All checks passed —— 实际均通过。

运行实测（2026-08-25 23:47 重启 backend 后，每 2.5s 采样 HTTP latency 持续 30+ 分钟）：
- 首 tick（一次性迁移）峰值 1.4s，期间 HTTP 始终有响应
- 第二 tick 起稳态：最大 689ms 波动（纯 Python scan），全程 6ms 基线，无无响应、无 agent 掉线
- py-spy dump：rag-warmup 线程已退出（模型预加载完成），进程全 idle

追加（2026-08-26，group_send 半开发现与修复）：
$ py-spy dump 实测 dispatch_task 卡在 asgiref run_until_future/wait —— 根因 channels_redis group_send 半开连接忽略取消
修复：gaf_core/async_utils.call_async_with_timeout（worker 线程 Future.result(timeout)），dispatch 5s / 日志广播 2s
验证：修复后 dispatch POST 127-164ms 稳定返回；残留 RUNNING 清理 + 设备释放后排队不再卡死
$ conda run -n gaf python -m pytest backend/tasks/tests/test_execution_flow.py -q --tb=short   # 24 passed

$ D:\code\environment\conda\envs\gaf\Scripts\py-spy.exe dump --pid <backend_pid>