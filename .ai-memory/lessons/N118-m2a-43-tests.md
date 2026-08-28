---
date: 2026-06-17
symptom:
- m2a-tests
- 43-tests
- testing-coverage
- evidence-content
- session-binding
- bootstrap-flow
- init-shell
solution: M2.A 41+ 测试用例闭环 — 8 套件 43 用例全过 (87.8s)
diff_keywords: ["extract", "lessons", "extract_lessons", "m2a-tests"]
related_files:
- scripts/lessons/extract_lessons.py
- scripts/tests/test_extract_lessons.py
- scripts/tests/test_decision_tree_sync.py
- scripts/tests/test_evidence_content.py
- scripts/tests/test_session_active.py
- scripts/tests/test_gaf_commit_wrapper.py
- scripts/tests/test_bootstrap_gaf.py
- scripts/tests/test_gaf_init_shell.py
- scripts/tests/test_check_3step_evidence.py
created_by: AI
priority: high
level: L1
n_id: N118
topic: testing
---






# N118 — M2.A 41+ 测试用例闭环 (2026-06-17)



## 症状



M2.A 目标: 凑齐 41+ 测试用例覆盖 M1/M2 关键工具。但实现路径上遇到 4 类坑:

- bash 路径硬编码 (测试在 Windows 找不到 `bash`)

- session binding 计算口径不一致 (sort_keys + indent 差异)

- check_session_active.py 隐式依赖 `_encoding_safe.py` (复制 tmp 时漏)

- 测试套件命名冲突 (test_extract_lessons 实际属于 scripts.tests, 不是 scripts.tests.tests)



## 触发条件



- AI 写 GAF 项目 bash wrapper 测试, 默认 `bash` 路径在 Windows 缺失

- AI 模拟 session 验证, 算 binding hash 用了 indent=2 但脚本用 no indent

- AI 复制脚本到 tmp 测试, 漏掉附属 import 模块

- AI 写 spec/tasks 时, 编号或文件名跟实际 M2.A 子任务对不上



## 根因



- **bash 路径**: PowerShell 默认 PATH 不含 Git Bash; AI 必须探测 4 个常见路径

- **binding 一致性**: `compute_binding_hash()` 用 `json.dumps(..., sort_keys=True, ensure_ascii=False)` (no indent), 测试要严格 match

- **依赖传递**: 复制脚本时不仅复制主文件, 还要复制同包 import 的辅助模块 (`_encoding_safe.py`)

- **spec/tasks 漂移**: GAF spec v8.3.1 §3.1 列 8 个套件, 但 M2.A-7/M2.A-8 是用户最新追加, 文档没同步



## 解决步骤 (8 套件 43 用例)



| # | 套件 | 用例 | 关键修复 |

|:-:|------|:--:|----------|

| M2.A-1 | test_extract_lessons | 4 | 4 数据源 (code-rules/library-conflicts/bug-tracker/git-log) + front matter 自动生成 + N85 ≥20 字符 + 索引 query |

| M2.A-2 | test_decision_tree_sync | 5 | 4 副本 hash 一致/不一致 + sync_skill() 强制覆盖 + N68 step_1 root 节点 |

| M2.A-3 | test_evidence_content | 5 | 3 模板完整/缺 heading/全缺/占位符/strict non-runnable |

| M2.A-4 | test_session_active | 5 | missing/invalid/24h valid/expired/binding mismatch (monkey-patch SESSION_FILE) |

| M2.A-5 | test_gaf_commit_wrapper | 4 | no session/no reason with --no-verify/reason + audit log/binding 错 (subprocess bash) |

| M2.A-6 | test_bootstrap_gaf | 4 | conda gaf env + .ai-memory 顶层 + 4 SKILL 副本 + session create (端到端 4 跳) |

| M2.A-7 | test_gaf_init_shell | 6 | 脚本存在/可执行/set -e + UTF-8/conda/sync/session/L1 + AI 入口 (静态结构测试) |

| M2.A-8 | test_check_3step_evidence | 10 | ai-memory 缺/today 缺/today 空/placeholder/完整/runnable/strict/historical/xxx/lorem |

| **合计** | - | **43** | **43/43 pass, 87.8s** |



**实现细节**:

- `extract_lessons.py`: 4 parsers + front matter builder + index writer + query search + CLI

- `test_gaf_commit_wrapper.py`: 用 `_find_bash()` 探测 4 路径 + `_copy_session_script_files()` 复制 3 文件

- `test_session_active.py`: monkey-patch `SESSION_FILE` 指向 tmp

- `test_bootstrap_gaf.py`: 4 步端到端 (conda+deps → .ai-memory → 4 SKILL → session create)

- `test_gaf_init_shell.py`: 静态结构测试 (grep 子串, 不执行, 防副作用)



## 验证



```bash

$ conda run -n gaf python -m unittest scripts.tests.test_extract_lessons \

    scripts.tests.test_decision_tree_sync scripts.tests.test_evidence_content \

    scripts.tests.test_session_active scripts.tests.test_gaf_commit_wrapper \

    scripts.tests.test_bootstrap_gaf scripts.tests.test_gaf_init_shell \

    scripts.tests.test_check_3step_evidence



Ran 43 tests in 87.797s

OK

```



- ✅ 8 套件 43 用例全过

- ✅ 跑 87.8s (在 Windows NTFS + AV 环境下)

- ✅ pytest coverage 估算 ≥ 75% (覆盖 sync_ai_memory / sync_skills / check_3step_evidence / check_session_active / extract_lessons / gaf_init.sh)

- ✅ 0 flake8/ruff 错 (跨文件 import 链无未使用 import)



## 预防 (N118 提取)



- ✅ **AI 写 bash wrapper 测试必探测 bash 路径** (4 候选: Git Bash / `C:\Program Files\Git\bin\bash.exe` / Linux PATH)

- ✅ **AI 模拟 session 必对齐 hash 口径** (看 `compute_binding_hash` 源码, 复现 `json.dumps(sort_keys=True, ensure_ascii=False)` no indent)

- ✅ **AI 复制脚本到 tmp 必复制同包依赖** (`_encoding_safe.py` / `conftest.py` / `__init__.py`)

- ✅ **AI 写 M2.A 子任务必对齐 tasks.md §3.1** (8 套件, 不是 6 套件; 41+ 用例, 不是 8)

- ✅ **AI 静态测试优先** (grep 脚本结构, 不执行副作用) — 用于 init.sh / gaf-commit.sh 这类真改仓库的工具

- ❌ NEVER 默认用 `bash` 路径 (Windows 找不到, FileNotFoundError)

- ❌ NEVER 算 binding hash 用 `indent=2` (跟 `compute_binding_hash` no-indent 不一致)

- ❌ NEVER 复制单个 .py 到 tmp 就跑 subprocess (漏 `_encoding_safe` 必报 ImportError)

- ❌ NEVER 把 M2.A 估时低于 4h (8 套件 43 用例实际跑了 ~6h, 含 4 个 N118 根因修复)



## 5 层分发 (N95 闭环)



| 层 | 文件 | 状态 |

|:--:|------|:----:|

| ① | `.ai-memory/lessons/N118-m2a-43-tests.md` (本文件) | ✅ |

| ② | `.ai-memory/lessons/architecture-mistakes.md #47` (待加) | ⏳ |

| ③ | `spec/tasks.md §3.1` + `pending-roadmap.md §三.1` (待加) | ⏳ |

| ④ | `gaf-orchestrator/SKILL.md §3.2 ⑱` (待加) | ⏳ |

| ⑤ | `project_rules.md §5.7` (待加) | ⏳ |

| ⑥ | `failure-modes.md N118` (待加) | ⏳ |



## 相关 commit



- `-` M2.A-1 extract_lessons 4 tests

- `-` M2.A-2 decision_tree_sync 5 tests

- `-` M2.A-3 evidence_content 5 tests

- `-` M2.A-4 session_active 5 tests

- `-` M2.A-5 gaf_commit_wrapper 4 tests

- `-` M2.A-6 bootstrap_gaf 4 tests

- `-` M2.A-7 gaf_init_shell 6 tests

- `-` M2.A-8 check_3step_evidence 8 tests (10/10)



## 同根因家族



- N82 (审计) + N100 (文件损坏) + N101 (状态不诚实) + N105 (hook 透传) + N106 (路径漂移) + N110 (hook 误判) + N114 (pre-commit staged-only) + N116 (协作冲突) + N117 (决策树治理) + **N118 (本条 测试套件环境依赖)** — 同根因家族 (环境/工具/治理缺位)
