---
maintainer: manual
source: .trae/specs/2026-07-19-spec41-doc-health-checker-design.md
load_when: [doc-health, spec-42, L3-1 扫描]
priority: high
symptom:
- doc-health-report
- 文档健康报告
- doc_health_report.json
solution: spec-41 静态层 7 维度报告 schema 说明, AI 会话启动时 Read .cache/doc_health_report.json
related_files:
- scripts/governance/doc_health_check.py
- scripts/governance/report_schema.py
created_by: AI
last_manual_edit: 2026-07-19
---

# Doc Health Report Schema (spec-41)

> AI 会话启动时 Read `.cache/doc_health_report.json` 消费本报告。
> 详细设计见 `.trae/specs/2026-07-19-spec41-doc-health-checker-design.md` §4。

## JSON Schema 概要

```json
{
  "generated_at": "ISO 8601 timestamp",
  "git_sha": "short git SHA at report generation",
  "duration_seconds": 1.82,
  "summary": {
    "total": 12,
    "by_severity": {"P0": 1, "P1": 5, "P2": 6},
    "by_dimension": {
      "d1_overlap": 2, "d2_bloat": 1, "d3_count_drift": 0,
      "d4_path_drift": 1, "d5_frontmatter": 0,
      "d6_staleness": 5, "d7_index_consistency": 3
    }
  },
  "issues": [
    {
      "id": "12-char sha1 hash (stable)",
      "dimension": "d4_path_drift",
      "severity": "P0",
      "file": ".ai-memory/lessons/x.md",
      "line": 8,
      "evidence": "description of the issue",
      "suggested_fix": "actionable fix hint",
      "root_cause_hint": "why this happens",
      "consumed": false
    }
  ]
}
```

## 7 维度速查

| 维度 | 含义 | severity 默认 |
|-----|-----|-------------|
| d1_overlap | 职责重复 (Jaccard summary 相似度) | P2/P1 |
| d2_bloat | 内容膨胀 (单文件行数超阈值) | P2/P1/P0 |
| d3_count_drift | 计数漂移 (硬编码 vs 实际) | P2/P1 |
| d4_path_drift | 路径漂移 (frontmatter/body 路径不存在) | P0 |
| d5_frontmatter | frontmatter 三模式合规 (auto/derived-manual/manual) | P1/P2 |
| d6_staleness | 文档时效 (last_updated + commit lookback) | P2/P1/P0 |
| d7_index_consistency | 索引一致性 (failure-modes vs lessons/README vs yn-matrices) | P1/P2 |

## AI 消费协议

1. AI 会话启动 (gaf-orchestrator L1 hard-load) 时 Read 本文件
2. 若 total > 0, 在会话首条消息附"⚠️ doc health: N issues (P0:X/P1:Y/P2:Z)"
3. 若 P0 > 0, 强制提示用户"启动后建议先跑 L3-1 扫描处理 P0 issues"
4. L3-1 扫描时按 P0 → P1 → P2 优先级处理, 处理后标 consumed=true
5. issue.id 是稳定 hash (基于 dimension+file+line+evidence), 同一问题多次扫描 id 不变

## 触发时机

- **gaf_init.sh --full 启动时** (静态层, <2s)
- **手动**: `python scripts/governance/doc_health_check.py`
- **不阻塞对话**: 报告 JSON 一次性 Read, 对话中零额外开销
