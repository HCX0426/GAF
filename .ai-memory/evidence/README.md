---
maintainer: ai
source: GAF/.ai-memory/evidence/
load_when: [evidence, 3-step-evidence, 反思, 写教训, self-evolution]
priority: high
symptom: [kb:evidence-layout, active-archived-rotation, sedimentation-rule]
solution: evidence 三档目录 — active/ (30 天内待沉淀) + archived/YYYY-MM/ (30 天以上已沉淀或过期) + templates/ (模板); 同 topic ≥ 2 触发主动沉淀
related_files:
  - .ai-memory/evidence/templates/problem.md
  - .ai-memory/evidence/templates/solution.md
  - .ai-memory/evidence/templates/verification.md
  - .ai-memory/lessons/README.md
  - .skills/skills/gaf-orchestrator/SKILL.md
  - backend/gaf_core/startup_checks.py
created_by: AI
last_updated: 2026-07-26
---

# GAF Evidence 目录说明 (spec §4.1)

## 三档目录结构

```
.ai-memory/evidence/
├── active/                  # 30 天内, 待沉淀
│   └── YYYY-MM-DD-<slug>/
│       ├── problem.md
│       ├── solution.md
│       └── verification.md
├── archived/                # 30 天以上, 已沉淀或过期
│   └── YYYY-MM/
│       └── YYYY-MM-DD-<slug>/
└── templates/               # 3 步证据模板 (problem/solution/verification)
    ├── problem.md
    ├── solution.md
    └── verification.md
```

## 沉淀规则 (spec §4.1 步骤 ③)

**触发条件**: AI 会话启动时扫 `evidence/active/`,同 topic 出现次数 ≥ 2 → 标记 `pending_promotion`

**主动沉淀流程** (spec §4.1 步骤 ③):
1. AI 在当前会话内处理 `pending_promotion`
2. 写新 lesson 文件到 `.ai-memory/lessons/N<编号>-<slug>.md`
3. 更新 `.ai-memory/meta/failure-modes.md` §Active 表格
4. 移 evidence 目录从 `active/` 到 `archived/YYYY-MM/`

## 自动清理 (spec §5.2, `startup_checks.py`)

GAF 启动时跑一次 (非定时任务):
- `cleanup_old_evidence_once()`: active > 30 天 → 移到 `archived/YYYY-MM/`
- `delete_archived_evidence_once()`: archived > 90 天 → 删除

## 手动操作

```bash
# 查看 active evidence 列表
ls .ai-memory/evidence/active/

# 手动触发清理 (dry-run)
conda run -n gaf python manage.py run_startup_checks --dry-run

# 实际清理
conda run -n gaf python manage.py run_startup_checks
```

## 与 lessons 的关系

| 阶段 | 位置 | 用途 |
|------|------|------|
| ① 收集证据 | `evidence/active/` | 3 步证据 (problem/solution/verification) |
| ② 触发沉淀 | 同 topic ≥ 2 | AI 标记 `pending_promotion` |
| ③ 写 lesson | `lessons/N<编号>-<slug>.md` | 提炼为可复用教训 |
| ④ 归档 evidence | `evidence/archived/YYYY-MM/` | 原始证据保留备查 |
| ⑤ 90 天后删除 | — | 自动清理 |

## 触发点 (gaf-orchestrator SKILL.md §4.2)

- **触发点 1** (会话启动): AI 启动时扫 `evidence/active/` 同 topic 出现次数 ≥ 2 → `pending_promotion`
- **触发点 3** (闭环步骤 5): AI 写完新 evidence 后扫,同 topic ≥ 2 → 触发 §4.1 步骤 ③ 主动沉淀
