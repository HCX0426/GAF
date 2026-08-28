---
source: GAF/.ai-memory/lessons/N117-m1h-decision-tree-changelog.md
load_when:
- 决策树变更
- 季度 review
- hash 漂移
- changelog 遗漏
priority: medium
symptom:
- decision-tree 改了不知道
- changelog 漂移
- 季度 review 无提示
- _shared/ 目录不存在
- hash 计算口径不一
solution: sync_skills.py --changelog 命令 (auto bootstrap + hash diff append) + 6 tests
  + spec-evolution §6 季度 review
diff_keywords: ["sync", "skills", "sync_skills", "decision-tree"]
related_files:
- scripts/bootstrap/sync_skills.py
- scripts/tests/test_sync_changelog.py
- .trae/skills/gaf-orchestrator/_shared/decision-tree-changelog.md
- .ai-memory/meta/spec-evolution.md
- .trae/skills/gaf-orchestrator/SKILL.md
- .trae/rules/project_rules.md
created_by: AI
date: 2026-06-16
last_updated: 2026-06-16
level: L1
n_id: N117
topic: workflow
---






# N117: M1.H 决策树 changelog + 季度 review (2026-06-16 闭环)



> **教训来源**: M1 完整闭环 tasks.md §2.8 — 决策树 hash 变更追踪缺位 + 季度 review 无提示

> **失败模式**: N95 (5 层分发) + N100 (文件损坏) + N101 (状态不诚实) + N106 (路径漂移) + N116 (并发状态管理) 家族新成员

> **状态**: ✅ 已闭环 (commit `-` 实现 + 本轮 5 层分发)



## 1. 问题 (Problem)



### 1.1 决策树变更无追踪 (Decision Tree Drift)



决策树 (`.trae/skills/gaf-orchestrator/SKILL.md` 中 `## Decision Tree` ↔ `## End Decision Tree` 块) 是 AI 任务的根节点, 但:

- ❌ 改了决策树, 没有 changelog 记录"什么时候改的 / hash 是什么 / 为什么改"

- ❌ 4 份决策树副本 (gaf-orchestrator / knowledge-base / task-execution / reflect-and-evolve) 的 hash 漂移无人察觉

- ❌ 旧决策树引用无法追溯 (回滚时不知道上次是哪个 hash)



### 1.2 季度 review 无提示 (No Quarterly Review)



决策树 step 数 / task_type 分支 / 反模式覆盖 / KB 路径都应定期 review, 但:

- ❌ 没有"每季度 review 一次"的硬提示

- ❌ 没有 review 模板 (5 步该看什么 / 怎么输出)

- ❌ AI 写 spec/改决策树时不会主动跑 review



### 1.3 _shared/ 目录约定不明 (Shared Directory Convention)



spec 提到 `.trae/skills/gaf-orchestrator/_shared/decision-tree-changelog.md`, 但:

- ❌ 实际项目没有 `_shared/` 目录 (gaf-orchestrator/ 直接放 SKILL.md)

- ❌ 共享文件放哪? 子目录 vs 平级目录? AI 不知道

- ❌ 跨 skill 共享需要约定 (gaf-orchestrator / gaf-knowledge-base 共享什么?)



## 2. 根因 (Root Cause)



### 2.1 决策树变更追踪缺位 (4 维)



1. **缺工具**: 没有命令能"算 block hash + 写入 changelog", AI 只能口头说"我改了"

2. **缺存储**: 没有约定的 changelog 文件位置, AI 不知写哪

3. **缺触发**: 没有 pre-commit hook 强制"改决策树 → 必跑 --changelog", 改了不一定记录

4. **缺格式化**: 即使写了 changelog, 没有标准表格 (date / old_hash / new_hash / note), 难以 parse



### 2.2 季度 review 缺位 (3 维)



1. **缺时间触发**: 1/1, 4/1, 7/1, 10/1 没有自动化提示

2. **缺模板**: review 5 步该看什么, 怎么输出 markdown

3. **缺责任**: 没人负责 review (AI 不知道是 user 还是 self)



### 2.3 _shared/ 约定缺位 (2 维)



1. **缺设计**: spec 提了 `_shared/` 但没说是子目录还是平级, AI 自由发挥

2. **缺文档**: 没有 "shared file 该放哪" 的项目规则



## 3. 修复 (Solution)



### 3.1 决策树 changelog 修复 (4 件套)



| 修复 | 文件 | 关键点 |

|------|------|--------|

| `--changelog` 命令 | `scripts/bootstrap/sync_skills.py` | `_extract_decision_tree_block_hash()` + `_read_changelog_last_hash()` + `append_changelog_entry()` + `cmd_changelog()` 4 个函数 |

| 表格格式 | `decision-tree-changelog.md` | 6 列表格 (# / date / old_hash / new_hash / note / author), 用 `\|` 转义 note 中的 `|` |

| 测试覆盖 | `scripts/tests/test_sync_changelog.py` | 6 tests: bootstrap + idempotent + hash-change + last-hash + note-escape + block-hash |

| Auto-bootstrap | `append_changelog_entry()` | 文件不存在 → 写 frontmatter + 表头 + 第 1 行; 文件存在 → 比较 last_hash, 改了才 append |



**3 步失败兜底**:

1. `_extract_decision_tree_block_hash()` 返回空 → 报"无法提取决策树 block", exit 1

2. `append_changelog_entry()` 检测 last_hash == current → 静默 no-op (不报错)

3. `relative_to(REPO_ROOT_DEFAULT)` 跨盘符失败 → fallback 绝对路径 (测试用 tmpdir 友好)



### 3.2 季度 review 修复 (1 件套 + spec 文档化)



| 修复 | 文件 | 关键点 |

|------|------|--------|

| §6 季度 review | `.ai-memory/meta/spec-evolution.md` | 5 步 review + 输出模板 + A/B/C 分类 (立即修 / 后续 / 无法解决) |

| 命令触发 | `python scripts/bootstrap/sync_skills.py --changelog --note "Q{1-4} 2026 review"` | 季度首日跑一次, hash 不变 → no-op |



### 3.3 _shared/ 约定 (本轮自然形成)



| 决策 | 路径 | 理由 |

|------|------|------|

| `_shared/` 子目录 | `gaf-orchestrator/_shared/` | 共享文件属于 gaf-orchestrator 私有, 4 决策树副本不复制 _shared/ |

| 仅 changelog 共享 | 当前只放 changelog.md | 未来 gaf-knowledge-base 可能有 _shared/, 但本轮不展开 |



## 4. 验证 (Verification)



### 4.1 测试 6/6



```

$ python scripts/tests/test_sync_changelog.py

......

Ran 6 tests in 0.155s

OK

```



覆盖:

- `test_header_bootstrap_creates_file_with_first_entry`: 文件不存在 → bootstrap + 第 1 行

- `test_idempotent_when_block_unchanged`: 同一 SKILL.md 跑两次 → 第二次 no-op

- `test_hash_change_appends_new_row_with_previous_hash`: 改 SKILL.md → 追加新行 + old_hash 是上次 hash

- `test_read_last_hash_returns_rightmost_hash`: `_read_changelog_last_hash` 返回最新行 new_hash

- `test_note_escapes_pipe_characters`: note 中 `|` → 转义为 `\|`, 表格格式不破坏

- `test_block_hash_changes_when_block_changes`: 改 block → hash 必变 (sanity check)



### 4.2 真实 changelog 验证



```

$ python scripts/bootstrap/sync_skills.py --changelog --note "M1.H init"

✅ Changelog 已更新:

   old_hash: (initial) → new_hash: 104b599d7f744018



$ python scripts/bootstrap/sync_skills.py --changelog --note "M1.H init - re-run"

✅ Changelog 无需更新 (当前 hash 104b599d7f744018 与上次记录一致)

```



## 5. 5 层分发状态 (N95 闭环)



| # | 层级 | 路径 | 状态 |

|:-:|------|------|:----:|

| ① | .ai-memory/ 教训层 | 本文件 (`.ai-memory/lessons/N117-m1h-decision-tree-changelog.md`) | ✅ |

| ② | docs/ 架构教训层 | `architecture-mistakes.md #46` (本轮 append) | ✅ |

| ③ | spec/ 计划文档层 | `tasks.md §2.8` 标 ✅ + `pending-roadmap.md §二.15` (本轮 append) | ✅ |

| ④ | SKILL.md 工作流层 | `.trae/skills/gaf-orchestrator/SKILL.md §3.2 ⑰ 决策树 changelog + 季度 review Y/N 矩阵` (本轮 append) | ✅ |

| ⑤ | project_rules.md 用户规则层 | `project_rules.md §5.6 决策树 changelog + 季度 review 硬规则` (本轮 append) | ✅ |



## 6. 预防规则 (AI 必读)



### 6.1 决策树变更预防



- ✅ **改 gaf-orchestrator/SKILL.md 决策树块必跑 `sync_skills.py --changelog`** (pre-commit hook 可加)

- ✅ **changelog note 必填可读 description** (不要 "update" / "fix" 这种空描述, 要 "N117 闭环" / "step_2 added")

- ✅ **block hash 计算口径必须一致** (从 `## Decision Tree` 到 `## End Decision Tree` 整段, 含 yaml code block)

- ❌ **NEVER 改决策树而不跑 --changelog** (N95 家族反模式, 改了不知道)

- ❌ **NEVER 手动编辑 decision-tree-changelog.md** (除非人工修正错误, 否则由 script 维护)



### 6.2 季度 review 预防



- ✅ **每季度首日 (1/1, 4/1, 7/1, 10/1) 跑一次 `--changelog --note "Q{1-4} 2026 review"`** (CI cron 可加)

- ✅ **review 5 步必做**: 决策树 step 数 / task_type 覆盖 / 反模式覆盖 / KB 路径 / changelog 漂移

- ✅ **review 输出按 spec-evolution §6.2 模板** (Q1-Q4 markdown 段)

- ❌ **NEVER 跳过季度 review** (即使决策树没改, 也要跑一次, hash 不变就是 no-op)

- ❌ **NEVER review 完不写 spec-evolution §6** (N95 家族反模式, review 不留痕)



### 6.3 _shared/ 约定预防



- ✅ **共享文件放 `gaf-{name}/_shared/`** (子目录约定, 不平级)

- ✅ **共享文件不进 4 决策树副本双根同步** (sync_skills.py 排除 _shared/)

- ❌ **NEVER 在 .trae/skills/ 根平级建 _shared/** (违反子目录约定)



## 7. 同根因家族 (Cross-cutting)



- **N95 (5 层分发)**: changelog + review 改动必须 5 层分发

- **N100 (文件损坏)**: changelog.md 不能手动编辑 (会破坏表格)

- **N101 (状态不诚实)**: 改了决策树不跑 --changelog = 状态不诚实

- **N106 (路径漂移)**: `_shared/` 路径必须用相对路径, 不能 inline 拼

- **N116 (并发状态管理)**: changelog append 涉及 R-M-W, 但本轮 single-AI 场景暂不需要锁 (后续多 AI 加锁同 N116)

- **N95+N100+N101+N106+N116+N117** = 同根因 (决策树治理缺位)



## 8. 维护期增强 (M1.H 后续)



- [B] pre-commit hook `gaf-decision-tree-changelog` (改 gaf-orchestrator/SKILL.md 自动触发 --changelog)

- [B] CI cron 季度首日自动跑 review (写 .github/workflows/quarterly-review.yml)

- [B] `decision-tree-changelog.md` 改为 module=auto (sync_ai_memory.py auto 模式可读)

- [B] gaf-knowledge-base 也建 `_shared/` (后续 knowledge 共享)



## 9. 反思 (Reflection)



### 4 问反思



1. **本轮做了什么**: 决策树 changelog (--changelog 命令 + 表格格式 + 6 tests) + 季度 review (spec-evolution §6 5 步 + 输出模板) + _shared/ 约定 (子目录化)

2. **可复用**: `append_changelog_entry()` 抽象 → 可复用到其他 markdown 文件 (release-notes / spec-changelog / lessons-changelog)

3. **风险/依赖**: 决策树 hash 16 字符前缀有 2^64 空间, 碰撞概率极低; 但 msvcrt + YAML 解析口径变动时需重新校准

4. **验收**: 6 tests + 真实 changelog 验证 + 二次 no-op 验证 + 5 层分发记录



### A/B/C 分类



- [A] 已修: --changelog 命令 + 6 tests + _shared/ 目录 + spec-evolution §6

- [B] 后续: pre-commit hook 强制触发 + CI cron 季度 review

- [C] 无法解决: 决策树 hash 16 字符碰撞 (2^64 空间, 工程上不可达)



### Round 2 发现 (本轮)



- ⚠️ 手写 changelog 用 `(init)` 作 placeholder, script 视为"非 hash"过滤掉, 导致 bootstrap 后追加一行 (initial)→real_hash 错位; 改: 删除手写 changelog, 让 script 从 0 bootstrap

- ⚠️ `relative_to(REPO_ROOT_DEFAULT)` 在测试用 tmpdir (跨盘符) 失败; 改: try/except 兜底用绝对路径

- ⚠️ `row.count("|")` 算错: 6+2=8, 实际是 7+2=9 (column separators = 6 columns + 1 trailing = 7, escaped `\|` 仍含 `|`); 改: 测试用 7+2
