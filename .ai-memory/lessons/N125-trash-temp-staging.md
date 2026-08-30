---
date: 2026-06-21
symptom:
- trash
- temp-file
- staging
- gitignore
- manifest
solution: AI 对话期间临时脚本 (_temp_*.py / _commit_msg.txt / _test_*.py / _*.log) 必须放 GAF/.trash/,
  不散落仓库根目录; .trash/ 不追踪 git (.gitignore 已忽略); 每个文件在 .trash/ manifest 表登记用途和创建时间;
  对话所有任务结束后统一清理 .trash/ (只留 README.md)
diff_keywords: ["trash", "temp-file", "staging", "gitignore", "manifest"]
related_files:
- .gitignore
- .trae/rules/project_rules.md
l2_candidate: true
created_by: AI
level: L1
n_id: N125
topic: workflow
---








# N125: .trash/ 临时文件暂存区机制



## 症状



1. **临时脚本散落仓库根目录**: AI 对话期间创建的 `_temp_*.py` / `_commit_msg.txt` / `_test_*.py` / `_*.log` 等临时文件直接放在 `` 根或 workspace 根, 跨对话残留

2. **用户需手动清理**: 每次对话结束后, 用户需要手动 `Remove-Item` 清理这些临时文件, 体验差

3. **临时文件被 git 追踪风险**: 散落的临时文件可能被误 `git add -A` 提交, 污染仓库



## 根因



- **无统一暂存区**: 仓库没有专门的临时文件目录, AI 默认写到 cwd (仓库根)

- **无 manifest 登记**: 临时文件无登记, 跨对话无法追溯用途

- **无对话结束清理流程**: AI 完成任务后不主动清理, 残留交给用户



## 修复



1. **建立 .trash/ 目录**:

   - 路径: `.trash/`

   - .gitignore 添加 `.trash/` 条目 (不追踪 git)

   - README.md 含规则说明 + manifest 表 (文件名 / 用途 / 创建时间 / 状态)

2. **AI 流程 (4 步)**:

   - 步骤 1: 需要临时脚本 → 写到 `.trash/<filename>`

   - 步骤 2: 在 `.trash/` manifest 表登记

   - 步骤 3: 使用完毕后保留 (对话中途可能再用)

   - 步骤 4: 对话所有任务结束 → 清空 .trash/ (只留 README.md)

3. **规则提升到 project_rules.md §5.11**:

   - 临时脚本放 .trash/ (不散落根目录)

   - .trash/ 不追踪 git

   - `.trash/` manifest 登记

   - 对话结束统一清理

   - 禁止放业务脚本 (需复用的放 scripts/ 并加测试)



## 5 层分发



| # | 层级 | 路径 | 状态 |

|:-:|------|------|:----:|

| ① | .ai-memory/ 教训层 | `.ai-memory/lessons/N125-trash-temp-staging.md` (本文件) | ✅ |

| ② | docs/ 架构教训层 | `.ai-memory/summaries/architecture-mistakes.md` (新增 #52 条目) | ⏳ |

| ③ | spec/ 计划文档层 | `docs/pending-roadmap.md §二.19` | ✅ |

| ④ | SKILL.md 工作流层 | `.trae/skills/gaf-orchestrator/SKILL.md §3.2 ⑳` (N125 Y/N 矩阵) | ⏳ |

| ⑤ | project_rules.md 用户规则层 | `§5.11 N125 .trash/ 临时文件暂存区` | ✅ |

| 附 | failure-modes.md | `.ai-memory/meta/failure-modes.md N125` | ⏳ |



## 验证



- `.gitignore` 含 `.trash/` 条目 ✅

- `.trash/` 含 manifest 表 ✅

- `project_rules.md §5.11` 含 N125 规则 ✅

- commit: - chore(rules): N125 .trash/ temp file staging area



## 🆕 2026-07-06 强化：禁止子目录 .trash/



**触发**: 用户反馈 "`.trash` 临时文件夹，统一在这，规则或者skill补上去，不要在其他地方建立了"



**发现违规**:

- `worker/src/.trash/` (2 文件)

- `backend/.trash/` (80+ 文件)

- `frontend/.trash/` (20+ 文件)



**根因**: N125 原文只说"放 `.trash/`"，未明确"唯一目录是 `.trash/`"，AI 在 backend/frontend 子目录工作时图方便就地建 `.trash/`。



**强化约束**:

- ✅ **唯一临时目录**: `.trash/`（项目根级）

- ❌ **禁止**: 在 `agent/`、`backend/`、`frontend/`、`worker/src/` 等任何子目录下另建 `.trash/`

- ✅ `.gitignore` 的 `.trash/` 通配规则已覆盖所有子目录（验证: `git check-ignore -v backend/.trash/test_import.py` → `.gitignore:143:.trash/`）

- ✅ project_rules.md N125 条目强化（2026-07-06）



**处理现有违规文件**: 不删除（N125 "任务中不删除"），但未来所有新临时文件必须放 `.trash/`。现有子目录 `.trash/` 文件由用户决定何时清理。
