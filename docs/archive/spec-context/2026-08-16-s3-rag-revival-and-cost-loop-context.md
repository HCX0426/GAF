# Spec-Context: S3 RAG Revival + Cost Loop (2026-08-16)

## 用户决策原文
- 2026-08-16 AI 大脑 + 工作流全面评估 Phase 1 获批后执行：S1 协议可靠性 → S2 恢复链接线 → S3 RAG 复活 + 诊断成本闭环 → 文档同步 + 每 spec 一次 commit
- "S2-2.7 agent 端界面恢复（yaml 状态机）单独排期，本 Phase 只接 backend 侧" — S2 范围收窄决策
- "3.5 幻觉防线先做基础版（evidence 字段 + 弱校验），强校验（检索比对）后续" — 幻觉防线范围决策（基础版实现 + 强校验登记已知限制）

## N151 5 步法评估
1. **架构盘点**: `gaf_ai` app 三条数据链路（RAG 索引 → ChromaDB 检索 / LLM 调用 → LLMUsageLog 记账 / ReAct 诊断 → AgentSession 轮询）；Task 模型字段为 execution_mode/task_definition/params_config（无 task_type/pipeline_config）；TD-116 已将 backend/ai 重命名 backend/gaf_ai
2. **识别反模式**: R1 索引路径引用已重命名目录（索引空目录静默 0 chunks）；R2 双价格表（llm_service MODEL_PRICING vs qa_cost_control PRICE_PER_1K_*，gpt-4o 0.005 vs 0.0025 冲突）；R3 工具读不存在的模型字段（get_task_config 永远返回默认值）；R4 AgentSession/QASession 无过期清理（RUNNING 永久 pending）；R5 诊断结果无证据字段（幻觉防线缺失）
3. **备选方案**: A) pricing.py 单价格源（无 Django 依赖，llm_service 非 Django 场景可 import）+ 各修复点最小改动 B) qa_cost_control 作为权威 + llm_service 反向 import（非 Django 场景会挂，拒绝） C) 只修路径不归一价格（半途而废，拒绝）
4. **拒绝反模式**: 拒绝 B（引入 Django 依赖破坏 llm_service 非 Django 契约）、C（双表继续漂移）；选 A
5. **AI 自决边界**: 幻觉防线强校验登记已知限制；test_retrieval_quality ChromaDB 空（TD-103 外部依赖）不阻塞；session 清理阈值（1h/24h/30d）自决合理默认

## N167 七维度评分
- **架构长远性**: pricing.py 单源是"价格只改一处"的自然终点，新增模型只改 1 文件 — 4
- **全局归一化**: 价格表双源 → 单源；路径引用重命名后统一到 gaf_ai — 4
- **新旧兼容**: estimate_cost 双契约保留（float vs Decimal）；LLMUsageLog 记账值不变（gpt-4o 0.0025/0.01 与 qa_cost_control 原值一致）；evidence 字段新增 default=list 无破坏 — 4
- **现有业务完善**: RAG 复活（真实索引 gaf_ai 代码）、get_task_config 真实返回、session 不再永久 pending — 4
- **性能资源优化**: 无性能影响；cleanup 每日 1 次低开销 — 3
- **安全合规加固**: 无涉 — 2
- **长期维护成本**: 价格表 2 处维护 → 1 处；路径 bug 不再静默 — 4
- **总分**: 25（方案 B 因破坏非 Django 契约否决，未评分）

## 关键实施决策
- **pricing.py 无 Django import**: llm_service 明确支持非 Django 上下文（smoke tests），qa_cost_control 反向 import 会挂；Decimal 值以记账契约为准（test_qa_cost_control 断言 0.007500/0.002500/0.010000 不变）
- **TD-068 conftest 补全（预存问题）**: gaf_ai/tests/ 单独跑 39 failed 全 429 — login throttle 5/min 未被禁用（全量 backend 跑时被 backend/tests/__init__.py 掩盖）。补 conftest.py + __init__.py（accounts 同模式，TD-336 #7 fixture 级 patch 可恢复）
- **auto_now_add 陷阱**: AgentSession/QASession 的 created_at 显式传值会被覆盖，测试用 queryset.update 绕过
- **beat 注册**: cleanup_stale_sessions 每日 3:00；检测 RUNNING>1h/PENDING>24h → FAILED 带 error_message（前端轮询不再永久 pending），QASession 无消息>30d 删除（有消息保留作知识来源）
- **幻觉防线基础版**: evidence JSONField（migration 0009）+ _parse_agent_result 提取 + 无 evidence 时 summary 附「[请人工复核]」注记（不阻塞）；强校验（evidence ↔ 检索比对）登记 spec 已知限制后续排期
- **get_task_config 契约**: 返回 execution_mode/task_definition/params_config 真实字段（原 task_type/pipeline_config 永远默认值/None 形同虚设）
- **hook infra GBK 崩溃（预存问题）**: auto_archive_specs.py + check_big_change.py 在 GBK console print emoji/ℹ️ → UnicodeEncodeError 阻塞 commit。修法: sys.stdout/stderr reconfigure(utf-8, errors=replace)（N105 hook 基础设施根因修复，N150 原则）
- **heartbeat malformed dispatch_sent_at**: 原空 except continue（R001 静默吞错）→ 视为 stale 重派/fail（防卡死 + N182 可观测性）

## N173 用时字段
- start_ts: 2026-08-16T16:40:00+08:00
- end_ts: 2026-08-16T18:05:00+08:00
- duration_min: ~85
- within_baseline: false（大修改基线 < 60 min）
- root_cause_if_over: 429 排查（39 failed → TD-068 conftest 缺失根因 + 修复 + 回归 3 轮）+ auto_now_add 陷阱 1 轮调试 + pre-commit 3 项 hook 修复（R001/GBK/B2/spec-context）耗时约 25 min，属测试隔离盲区 + hook 基础设施修复（N193 任务归属：预存问题纳入当前任务），非实现本身