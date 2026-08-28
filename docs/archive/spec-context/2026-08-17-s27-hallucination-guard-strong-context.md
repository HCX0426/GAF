# spec-context: 2026-08-17-s27-hallucination-guard-strong

> 承载体: spec-2026-08-17-s27-hallucination-guard-strong
> 关联: docs/specs/archived/2026-08/2026-08-17-s27-hallucination-guard-strong.md

## 1. 用户决策原文

- 用户 2026-08-17: "你按优先级来吧" (自决排序授权, §3.6) — P2 = 幻觉防线强校验
- 用户 2026-08-16 (S3 spec 阶段): "第3.5 幻觉防线这部分（evidence 字段 + 弱校验），强校验（检索比对）再排期"
  → S3 spec 已知限制: "幻觉防线强校验（evidence ↔ 检索结果比对）后续排期，本 spec 只做基础版"

## 2. N151 5 步法评估过程

1. **架构盘点**: `_run_agent_analysis` (backend/gaf_ai/tasks.py:80) 已有完整 ReAct 消息链
   (`reasoning_steps` 含 tool_name/observation, `_extract_reasoning_steps`:167);
   `text_similarity` (agent/tools.py:251, difflib.SequenceMatcher) 已是检索排序工具;
   `AgentSession.evidence` JSONField (migration 0009) + `_parse_agent_result` (tasks.py:244)
   已提取 evidence; 视图已透出 evidence (agent/views.py:232)
2. **识别反模式**: R1 手工规则堆叠 — 不用启发式正则匹配 evidence 文本;
   R2 双重检索 — 不重跑 RAG 查询, 复用已有 reasoning_steps 的 observations
   (工具调用链本身 = 检索结果, evidence 引用的是工具观测而非原始文档)
3. **A/B/C 备选**:
   - A) evidence ↔ reasoning_steps observations text_similarity 比对 (阈值 0.3),
     verified/unverified + summary 附注 + evidence_check 新字段
   - B) 重跑 RAG 检索比对 (额外 LLM/检索开销, evidence 语义与检索片段不对齐)
   - C) 只加注记不落库 (用户看不到校验结果, 不可追溯)
4. **拒绝反模式**: 拒绝 B (双检索开销 + 语义错位)、C (违反 N192 用户视角 B6);
   选 A
5. **AI 自决边界**: 阈值 0.3 (difflib ratio, evidence 是观测的转述, 低于 JSONL 检索的 0.5);
   unverified 附注最多列前 2 条; evidence_check 结构 `{verified: [...], unverified: [...]}`;
   兼容旧数据 (evidence_check 默认 None)

## 3. N167 七维度评分细节

| 维度 | 评分 | 说明 |
|------|------|------|
| 1 架构长远性 | 4 | 复用既有 reasoning_steps 链无新检索路径, 后续可升级 LLM 判定 |
| 2 全局归一化 | 4 | 复用 text_similarity, 不引第三套比对逻辑 |
| 3 新旧兼容 | 4 | evidence_check 默认 None, 旧 session 不受影响 |
| 4 现有业务完善 | 4 | 幻觉防线从"有无证据"升级到"证据是否被观测支撑" |
| 5 性能资源优化 | 4 | 纯 difflib 无网络/LLM 开销 |
| 6 安全合规加固 | 3 | 无凭据/敏感数据路径变化 |
| 7 长期维护成本 | 4 | 单函数 + 单字段, 测试独立覆盖 |
| **总分** | **27** | B: 21 (双检索+语义错位), C: 19 (不可追溯) → 领先 ≥ 5 → AI 自决 |

## 4. 关键实施决策

- `_verify_evidence` 放 tasks.py (与 _parse_agent_result 同模块, 数据流内聚), 延迟
  import `.agent.tools.text_similarity` 避免模块加载环
- 无工具调用 (observations 空) → 全部 unverified → 附强校验注记 (行为变化:
  单条 AI 消息无工具链的旧测试 test_task_stores_evidence_on_session 断言更新 —
  N193 任务归属: 行为变化属本任务, 更新旧测试而非绕过)
- `_tool_message` (SimpleNamespace) 类型名不是 'ToolMessage', _extract_reasoning_steps
  不识别 → 测试必须用 `_make_reasoning_tool_message` (类名构造) — 测试调试中发现
- 视图透出 `evidence_check or None` (旧数据兼容, 前端不用改)

## N173 用时字段

- `start_ts`: 2026-08-17T19:15:00+08:00
- `end_ts`: 2026-08-17T19:55:00+08:00
- `duration_min`: 40
- `within_baseline`: true
- `root_cause_if_over`: 含 test_agent 全量 129 测试 2 轮 + 强校验断言调试
  (difflib 转述相似度实测 0.26 < 0.3 → 调整测试用例); 大修改基线 < 60min 内