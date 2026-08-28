---
date: 2026-06-15
symptom:
- sync:path-mismatch
- sync:state-file-wrong-location
- spec:code:drift
- n106
- ai-memory-state
- sync-state-not-in-ai-memory
- repository-root-vs-ai-memory
solution: 修 sync_ai_memory.py line 471 用 `root / ".ai-memory" / "sync-state.json"`
  而非 inline `root / "sync-state.json"`;一次性 Move-Item 迁移 GAF/sync-state.json → GAF/.ai-memory/sync-state.json(保留
  30 条 change_history)
diff_keywords: ["sync", "ai", "memory", "sync_ai_memory", "path-mismatch"]
related_files:
- scripts/bootstrap/sync_ai_memory.py
- .ai-memory/meta/failure-modes.md
- .ai-memory/sync-state.json
- .gitignore
created_by: AI
priority: high
level: L1
n_id: N106
topic: cross-layer-sync
---




# N106: sync_ai_memory.py sync-state.json 写入路径不一致 (2026-06-16)



> **根因**: 代码写 `<root>/sync-state.json` (仓库根),spec §5 要求 `<root>/.ai-memory/sync-state.json`

> **触发条件**: 任何 sync_ai_memory.py 运行

> **影响**: `sync-state.json` 散落在仓库根,与 spec 不一致;gitignored 导致 `git status` 不显示变化,容易遗漏



## 1. 现象 (Symptom)



跑 `python scripts/bootstrap/sync_ai_memory.py --root GAF` 后:

- ✅ sync 跑通 (regenerated/skipped/read-only/warning 都正常输出)

- ❌ `sync-state.json` 出现在仓库根

- ❌ `.ai-memory/sync-state.json` 不存在

- ❌ `git status` 不显示 `sync-state.json` (因 `.gitignore` 排除,根路径)



## 2. 根因 (Root Cause)



`sync_ai_memory.py` 的 `update_sync_state()` 函数 (line 468):



```python

# Bug 代码

state_path = root / "sync-state.json"  # 写到仓库根

```



但 spec.md §5 完整目录树 (line 224) 明确写:



```

GAF/.ai-memory/

├── README.md

├── sync-state.json        # ← 应在 .ai-memory/ 下

```



而模块顶部 line 79 已定义 `SYNC_STATE = AI_MEMORY / "sync-state.json"` (正确路径),但 `update_sync_state()` 没用这个常量,直接 inline 拼路径。



## 3. 修复 (Solution)



**3.1 代码层 (sync_ai_memory.py)**:



```python

# 修复后

state_path = root / ".ai-memory" / "sync-state.json"  # 写到 .ai-memory/

```



**3.2 数据迁移 (一次性)**:



```powershell

Move-Item -Path "GAF\sync-state.json" -Destination "GAF\.ai-memory\sync-state.json" -Force

```



保留 30 条 `change_history`,不丢历史证据。



**3.3 加引用 SYNC_STATE 常量** (后续可优化):



未来应让 `update_sync_state()` 用 `SYNC_STATE` 常量(若 `root != REPO_ROOT_DEFAULT` 则用 `root / ".ai-memory" / "sync-state.json"`),避免再次漂移。



## 4. 验证 (Verification)



- [x] `sync-state.json` 不存在

- [x] `.ai-memory/sync-state.json` 存在 (6229 字节,30 条 history)

- [x] 重跑 sync_ai_memory,无破坏,read-only=0

- [x] 5 层分发闭环 (见下表)



## 5. 5 层分发 (N95 闭环)



| 层 | 路径 | 状态 |

|---|------|:---:|

| ① .ai-memory/ 教训层 | `.ai-memory/lessons/N105-commit-bypass-rollback.md` (N105) **+ 本文件 N106** | ✅ |

| ② docs/ 架构教训层 | `.ai-memory/summaries/architecture-mistakes.md` (待加 #34) | ⏳ |

| ③ spec/tasks/checklist 计划文档层 | `tasks.md M1.A.1` (本任务) | ✅ |

| ④ SKILL.md 工作流层 | `gaf-dev-workflow` §3.2 反思清单 (待加"路径一致性"项) | ⏳ |

| ⑤ project_rules.md 用户规则层 | `.trae/rules/project_rules.md` §5.2 (待加 SYNC_STATE 常量引用) | ⏳ |



## 6. 反思 (Reflection)



**4 问**:

1. **本轮要做什么?** 修 sync-state.json 路径不一致

2. **现有代码哪里直接复用?** `SYNC_STATE = AI_MEMORY / "sync-state.json"` 常量已存在,直接用

3. **潜在风险/依赖?** 数据迁移要保留 change_history (用 Move-Item 而非 copy+delete)

4. **验收标准?** `.ai-memory/sync-state.json` 存在 + `sync-state.json` 不存在 + sync 不破坏



**学习**:

- **inline 拼路径 = 漂移温床**: 模块级常量应作为 single source of truth,函数内 inline 拼路径极易与 spec 漂移

- **gitignore ≠ 不存在**: 文件被 gitignore 不代表它不存在,AI 必须 ls 检查实物而非依赖 git status

- **代码-文档漂移 = 隐性 bug**: 路径不一致不会让 sync 失败,但会让 spec 和现实脱节,后续 meta 工具读错位置就坏

- **M1.A.1 暴露的"第 11 份文件"问题**: spec 列出 sync-state.json 是 11 份顶层之一,但代码未实现 → 11 份变 10 份 + 1 个孤儿在根



## 7. 相关文件



- `scripts/bootstrap/sync_ai_memory.py` (line 79 SYNC_STATE 常量, line 471 update_sync_state)

- `.ai-memory/sync-state.json` (数据存储)

- `.gitignore` (line 133 `sync-state.json`)

- `build-gaf-knowledge-system spec (已删除)` (line 224 spec 定义)
