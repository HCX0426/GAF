---
spec_id: spec-2026-08-16-s3-rag-revival-and-cost-loop
title: S3 RAG 复活 + 诊断成本闭环 (索引路径修复 / 价格表归一 / get_task_config / session 清理 / 幻觉防线基础版)
status: ✅ 已归档 (docs/specs/archived/2026-08/2026-08-16-s3-rag-revival-and-cost-loop.md)
created: 2026-08-16
task_type: refactor
applies_to: [backend, gaf_ai]
---

# S3 — RAG 复活 + 诊断成本闭环

> 来源：2026-08-16 AI 大脑 + 工作流全面评估 Phase 1（S3）。评估结论：RAG 自动索引**实际索引了不存在的目录**（TD-116 重命名 `backend/ai` → `backend/gaf_ai` 后 `tasks_rag.py:41` 仍指向旧路径，`test_retrieval_quality` setup 断言 ChromaDB 空）；LLM 成本存在**双价格表**（`llm_service.py:55 MODEL_PRICING` vs `qa_cost_control.py:19 PRICE_PER_1K_*`，同一模型价格不同）；`get_task_config` 工具读不存在的字段（`task_type`/`pipeline_config`，Task 模型实际字段是 `execution_mode`/`task_definition`）；AgentSession/QASession 无过期清理；ReAct 诊断最终答案无证据字段（幻觉防线缺失）。
>
> **用户决策（2026-08-16 已确认）**：3.5 幻觉防线先做基础版（evidence 字段 + 弱校验），强校验（检索比对）后续。

## 阶段状态表

| 阶段 | 内容 | 状态 | 完成时间 | commit hash |
|------|------|------|---------|-------------|
| P1 | RAG 索引路径修复 (backend/ai → backend/gaf_ai) | ✅ | 2026-08-16 | - |
| P2 | 价格表归一 (MODEL_PRICING → PRICE_PER_1K 单源) | ✅ | 2026-08-16 | - |
| P3 | get_task_config 字段修复 | ✅ | 2026-08-16 | - |
| P4 | session 过期清理 (AgentSession/QASession beat 任务) | ✅ | 2026-08-16 | - |
| P5 | 幻觉防线基础版 (evidence 字段 + 弱校验) | ✅ | 2026-08-16 | - |
| P6 | 测试 + 文档同步 (含 TD-068 conftest 补全) | ✅ | 2026-08-16 | - |

## 任务清单

### P1: RAG 索引路径修复

- [x] `tasks_rag.py:41` 路径 `repo_root / 'backend' / 'ai'` → `repo_root / 'backend' / 'gaf_ai'`（TD-116 重命名残留，当前索引空目录）
- [x] 索引前校验目录存在（不存在打 warning，不静默返回 0）
- [x] `test_llm.py:465` 断言 `backend/ai` → `backend/gaf_ai` 同步
- [x] 新增 `test_auto_index_rag_warns_when_backend_dir_missing`（目录缺失 → warning + 只索引 agent）
- [x] 注释/docstring 残留路径同步（celery.py / test_retrieval_quality.py / test_llm.py / llm_router.py / tasks_rag.py）

### P2: 价格表归一

- [x] 新建 `gaf_ai/pricing.py` 单一价格源（无 Django 依赖，llm_service 非 Django 场景可安全 import）
- [x] `qa_cost_control.py` 删除本地价格表，改从 `pricing.py` import（记账契约不变：gpt-4o 0.0025/0.01、default 0.002/0.008）
- [x] `llm_service.py` 删除 `MODEL_PRICING`，`estimate_cost` 改从 `pricing.py` 读取（补入 gpt-3.5-turbo/qwen-max/claude-3.5-sonnet）
- [x] 两模块同模型价格一致（gpt-4o 价格统一为 0.0025/0.01，default 统一为 0.002/0.008）
- [x] 预存问题修复：`gaf_ai/tests/` 缺 TD-068 conftest → 单独跑 gaf_ai 目录时 login throttle 5/min 触发 429（39 failed）。补 `conftest.py` + `__init__.py`（accounts 同模式），467 passed

### P3: get_task_config 字段修复

- [x] `agent/tools.py:426-428` 用 `getattr(task, 'task_type', ...)` / `getattr(task, 'pipeline_config', None)` → 改为 Task 模型真实字段 `execution_mode` / `task_definition` / `params_config`
- [x] `test_agent.py` `GetTaskConfigTest::test_existing_task_returns_json` 断言同步为新字段

### P4: session 过期清理

- [x] `gaf_ai/tasks.py` 新增 `cleanup_stale_sessions`（AgentSession: RUNNING 超 1h / PENDING 超 24h → FAILED 带 error_message；QASession: 无消息超 30 天 → 删除，有消息保留）
- [x] `config/celery.py` beat 注册（每日凌晨 3:00）
- [x] 测试 5 个（running/pending 超时、fresh 保留、QA 删除/保留；auto_now_add 覆盖显式 created_at → 用 queryset.update 绕过）

### P5: 幻觉防线基础版 (evidence 字段 + 弱校验)

- [x] `AgentSession` 模型新增 `evidence` JSONField（migration 0009_agent_session_evidence）
- [x] `_parse_agent_result` 提取最终答案 JSON 的 `evidence` 数组（list/str 兼容）
- [x] `_run_agent_analysis` 存 evidence 到 session + 返回 dict；无 evidence 时 summary 附注「[请人工复核] 未提供证据条目」
- [x] `agent/views.py` 状态接口返回 `evidence` 字段
- [x] 测试：evidence 提取（含/不含两路径）+ 弱校验注记 + session 存储 + 状态接口返回

### P6: 测试 + 文档

- [x] RAG 路径测试（目录缺失 warning + 只索引 agent）
- [x] 价格表一致性（llm_service / qa_cost_control 均从 pricing.py 单源读取，无双表残留）
- [x] get_task_config 真实字段测试
- [x] session 清理测试 5 个
- [x] evidence 提取测试 13 个（含原 10 个解包更新）
- [x] 预存问题修复：gaf_ai/tests/ 缺 TD-068 conftest → 单独跑目录 429（39 failed）→ 补 conftest.py + __init__.py（accounts 同模式）
- [x] 文档同步：llm-integration.md §7.2 价格表改为引用 pricing.py
- [x] gaf_ai 全量回归：476 passed, 5 errors（ChromaDB TD-103 外部依赖）

## 实现产物清单 (2026-08-16 归档时补充)

- 代码: `backend/gaf_ai/pricing.py` (价格单源) / `tasks_rag.py` (索引路径修复) / `qa_cost_control.py` + `llm_service.py` (改读 pricing) / `tasks.py` (cleanup_stale_sessions + evidence 提取) / `agent/models.py` (evidence 字段) / `agent/tools.py` (get_task_config 真实字段) / `agent/views.py` (evidence 透出) / `migrations/0009_agent_session_evidence.py`
- 测试: `tests/conftest.py` + `__init__.py` (TD-068 throttle 禁用) + `test_llm.py` / `test_agent.py` / `test_anomaly_jsonl.py` / `test_retrieval_quality.py` 更新
- 文档: `docs/business/ai/llm-integration.md` §7.2 + `docs/standards/backend-conventions.md` JSONField 约定段

## 验收标准

1. auto_index_rag 索引 `backend/gaf_ai`（非空目录），ChromaDB 有真实 chunks
2. 同一模型在两模块估算成本一致
3. get_task_config 返回真实 execution_mode / task_definition
4. 过期 session 被清理，有消息的 QASession 保留
5. 诊断结果含 evidence 字段；无证据时有弱校验提示
6. 相关 pytest 全绿

## 已知限制

- ~~幻觉防线强校验（evidence ↔ 检索结果比对）后续排期，本 spec 只做基础版~~ → ✅ 已闭环 (spec-2026-08-17-s27-hallucination-guard-strong, commit 待回填)
- ChromaDB 索引依赖外部服务（TD-103），本地无 ChromaDB 时 retrieval_quality 测试跳过/报错不阻塞