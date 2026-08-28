---
spec_id: spec-2026-08-17-s27-hallucination-guard-strong
title: P2 — 幻觉防线强校验 (evidence ↔ 工具观测比对)
status: ✅ 已归档 (commit -, 2026-08-17)
archived_to: docs/specs/archived/2026-08/2026-08-17-s27-hallucination-guard-strong.md
created: 2026-08-17
task_type: new_feature
applies_to: [backend]
---

# P2 — 幻觉防线强校验 (evidence ↔ 工具观测比对)

> 来源: S3 spec (-) 已知限制 "幻觉防线强校验（evidence ↔ 检索结果比对）后续排期，本 spec 只做基础版"。用户授权"按优先级来"（2026-08-17），P2 = 强校验。
>
> **范围**: S3 P5 已实现弱校验（evidence 为空 → summary 附人工复核注记）。本 spec 实现强校验: 把 agent 最终答案的 evidence 条目与 ReAct 工具调用链的真实观测 (tool observations) 做文本相似度比对, 未找到支撑的 evidence 标记 unverified 并附注 — 从"只查有没有证据"升级到"查证据是否真的被工具观测支撑"。

## N151 5 步法评估

1. **架构盘点**: `_run_agent_analysis` (backend/gaf_ai/tasks.py:80) 已有完整 ReAct 消息链 (`reasoning_steps` 含 tool_name/observation, `_extract_reasoning_steps`:167); `text_similarity` (agent/tools.py:251, difflib.SequenceMatcher) 已是检索排序工具; `AgentSession.evidence` JSONField (migration 0009) + `_parse_agent_result` (tasks.py:244) 已提取 evidence; 视图已透出 evidence (agent/views.py:232)
2. **识别反模式**: R1 手工规则堆叠 — 不用启发式正则匹配 evidence 文本; R2 双重检索 — 不重跑 RAG 查询, 复用已有 reasoning_steps 的 observations (工具调用链本身 = 检索结果)
3. **备选方案**: A) 强校验 = evidence 与 reasoning_steps observations 的 text_similarity 比对 (difflib 复用), 阈值 0.3, 输出 verified/unverified + summary 附注 + 新增 evidence_check 字段; B) 重跑 RAG 检索比对 (额外 LLM/检索开销, evidence 语义与检索片段不对齐); C) 只加注记不落库 (用户看不到校验结果)
4. **拒绝反模式**: 拒绝 B (双检索开销 + 语义错位, evidence 引用的是工具观测而非原始文档)、C (校验结果不可追溯, 违反 N192 用户视角 B6); 选 A
5. **AI 自决边界**: 阈值 0.3 (difflib ratio, evidence 是观测的转述, 低于 JSONL 检索的 0.5 合理); unverified 附注最多列前 2 条; evidence_check 结构 `{verified: [...], unverified: [...]}`; 兼容旧数据 (evidence_check 默认 None)

## N167 七维度评分（方案 A）

- **架构长远性**: 强校验复用既有 reasoning_steps 链, 无新检索路径; 后续可升级为 LLM 判定 — 4
- **全局归一化**: 复用 text_similarity (单一相似度实现), 不引第三套比对逻辑 — 4
- **新旧兼容**: evidence_check 新字段默认 None, 旧 session 不受影响; 弱校验注记保留 — 4
- **现有业务完善**: 幻觉防线从"有无证据"升级到"证据是否被观测支撑", 补 S3 已知限制 — 4
- **性能资源优化**: 纯 difflib 比对无网络/LLM 开销 (evidence 条数 × observations 数, 量级极小) — 4
- **安全合规加固**: 无凭据/敏感数据路径变化 — 3
- **长期维护成本**: 单函数 `_verify_evidence` + 单字段, 测试可独立覆盖 — 4
- **总分**: 27 (B: 双检索 + 语义错位 21; C: 不可追溯 19) → 领先 ≥ 5 → AI 自决方案 A

## 阶段状态表

| 阶段 | 内容 | 状态 | 完成时间 | commit hash |
|------|------|------|---------|-------------|
| P1 | AgentSession.evidence_check JSONField + migration 0010 | ✅ | 2026-08-17 | - |
| P2 | `_verify_evidence` 函数 (evidence ↔ observations 比对) + 接入 _run_agent_analysis | ✅ | 2026-08-17 | - |
| P3 | 视图透出 evidence_check + summary 附注 | ✅ | 2026-08-17 | - |
| P4 | 测试 + 文档同步 | ✅ | 2026-08-17 | - |

## 任务清单

### P1: evidence_check 字段

- [x] `backend/gaf_ai/agent/models.py` AgentSession 新增 `evidence_check` JSONField (default=None, blank=True)
- [x] migration 0010_agent_session_evidence_check

### P2: 强校验逻辑

- [x] `backend/gaf_ai/tasks.py` 新增 `_verify_evidence(evidence: list[str], observations: list[str]) -> dict`:
  - 每条 evidence vs 每条 observation 用 `text_similarity` (from .agent.tools import text_similarity) 比对
  - max ratio >= 0.3 → verified; else unverified
  - 返回 `{"verified": [...], "unverified": [...]}`
  - evidence 为空 → 返回 `{"verified": [], "unverified": []}` (不改变弱校验行为)
- [x] `_run_agent_analysis`: 从 reasoning_steps 提取 observations (仅 ToolMessage 的 observation, 截断前 2000 字符已有) → 调 _verify_evidence → session.evidence_check 存储 + 返回 dict 加 evidence_check
- [x] unverified 非空 → summary 附注 `[强校验未通过] N 条证据与工具观测不符: <前 2 条>` (与弱校验注记不冲突, 弱校验注记保留)

### P3: 视图透出

- [x] `backend/gaf_ai/agent/views.py` 状态接口返回 `evidence_check` (默认 None)

### P4: 测试 + 文档

- [x] `backend/gaf_ai/tests/test_agent.py` 新增:
  - 全部 verified (evidence 与 observation 高度相似)
  - 部分 unverified (一条无支撑)
  - 全部 unverified
  - evidence 为空 → evidence_check 空 dict + 弱校验注记保留
  - 无工具调用 (observations 空) → 全部 unverified
  - 视图透出 evidence_check
- [x] 文档同步: S3 spec 已知限制标记已闭环 + llm-integration.md §7 (如涉及)

## 已知限制

- 阈值 0.3 是启发式 (evidence 为观测转述, 非原文); 后续可升级为 LLM 判定强校验
- 不强校验 summary 正文 (仅 evidence 数组)