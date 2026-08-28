---
date: 2026-06-21
symptom:
- script-duplication
- frontmatter-parsed-multiple-ways
- hardcoded-absolute-paths
- one-off-append-scripts
solution: >
  Consolidate one-off scripts into reusable tools, centralize frontmatter parsing,
  extend path consistency checks, and regenerate docs-index after script changes.
diff_keywords: ["frontmatter", "script-duplication"]
related_files:
- scripts/frontmatter.py
- scripts/lessons/append_lesson_block.py
- scripts/hooks/check_path_consistency.py
- scripts/bootstrap/sync_docs_index.py
- scripts/hooks/check_lessons_updated.py
- scripts/lessons/promote_lessons.py
- scripts/tests/test_gaf_commit_wrapper.py
- .trae/rules/project_rules.md
- .ai-memory/meta/docs-index.md
created_by: AI
priority: medium
level: L1
n_id: N122
topic: workflow
---




# N122: scripts/ 目录重复脚本与路径漂移



## Symptom



- `scripts/` 目录存在 10 个 `_append_*.py` 一次性脚本，功能几乎相同：向目标 Markdown 追加固定块。

- `sync_docs_index.py`、`check_lessons_updated.py`、`promote_lessons.py` 各自实现了近似的 YAML front matter 解析。

- `check_path_consistency.py` 原本只检查 basename 一致性，未检测脚本中的硬编码绝对路径。

- `test_gaf_commit_wrapper.py` 硬编码了不存在的 Git Bash 路径，导致本地测试失败。

- 脚本变更后 `docs-index.md` 未及时重建，e2e `test_documentation` 场景失败。

- `project_rules.md` 缺少 N91 14-hook 映射，导致 `test_n91_referenced_in_rules` 失败。



## Root Cause



- 早期按 N## 条目逐个生成 `_append_*.py`，没有抽象为参数化工具。

- Front matter 解析被视为每个脚本的“小逻辑”，未提取公共模块。

- 路径检查工具范围过窄，且测试 fixture 使用了开发者本地路径而非当前环境路径。

- 文档索引和规则引用未纳入脚本重构后的同步清单。



## Fix



1. **提取公共模块**

   - 新建 `scripts/frontmatter.py`，提供 `parse_front_matter(text)`。

   - `sync_docs_index.py`、`check_lessons_updated.py`、`promote_lessons.py` 统一导入。



2. **合并一次性脚本**

   - 新建 `scripts/lessons/append_lesson_block.py`，参数化 `--target --marker --block`。

   - 将 10 个 `_append_*.py` + `_refine_n91_failure.py` 移入 `scripts/archive/`（保留历史，但不再使用）。

   - 删除重复测试文件 `scripts/tests/test_session_active.py`（与 `scripts/tests/test_session_active.py` 重复）。



3. **扩展路径一致性检查**

   - `check_path_consistency.py` 增加 `ABS_PATH_RE`，检测 Windows 绝对路径字面量。

   - 支持 `# path-check-ignore` / `# noqa: path-check` 跳过有意保留的 fixture 路径。

   - 跳过文档字符串三引号内的路径示例，避免误报。



4. **修复测试与规则**

   - `test_gaf_commit_wrapper.py`：将 `List[str]/Tuple[...]` 改为 `list[str]/tuple[...]`；增加当前环境 Git Bash 路径；缺少 bash 时自动 skipTest。

   - `.trae/rules/project_rules.md`：补充 `### 5.8 N91 hook-failure 映射`，列出 14 hooks 及修复命令。

   - 跑 `python scripts/bootstrap/sync_docs_index.py` 重建 `.ai-memory/meta/docs-index.md`。



## Verification



```powershell

# ruff on modified files

D:\code\environment\conda\envs\gaf\python.exe -m ruff check `

  scripts/frontmatter.py scripts/bootstrap/sync_docs_index.py scripts/hooks/check_lessons_updated.py `

  scripts/lessons/promote_lessons.py scripts/hooks/check_path_consistency.py `

  scripts/lessons/append_lesson_block.py scripts/tests/test_gaf_commit_wrapper.py



# full scripts tests

D:\code\environment\conda\envs\gaf\python.exe -m pytest GAF/scripts/tests/ -p no:django

# result: 155 passed



# path consistency

D:\code\environment\conda\envs\gaf\python.exe GAF/scripts/hooks/check_path_consistency.py --root GAF

# result: 0 error, 66 warnings (pre-existing emulator paths)

```



## Rule



- 新增脚本前先检查 `scripts/` 是否已有同类工具，优先参数化复用。

- Front matter / YAML 解析必须复用 `scripts/frontmatter.py`。

- 修改脚本后必须跑 `sync_docs_index.py`，并检查 e2e `documentation` 场景。

- 测试 fixture 中的绝对路径必须加 `# path-check-ignore` 注释，并指向当前环境真实路径或优雅跳过。
