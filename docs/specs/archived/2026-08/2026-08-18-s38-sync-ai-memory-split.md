# s38 — Split `scripts/bootstrap/sync_ai_memory.py` (1384 lines) into domain modules (TD-365)

> TD-365 大文件治理 batch 5。s34-s37 已闭环。scripts 层第一个文件。

## 状态表

| Phase | 状态 | 完成时间 | commit | 验收 evidence |
|-------|------|---------|--------|--------------|
| P1 结构分析 + spec | ✅ | 20:36 | - | 6 域调用图 + patch 契约 + 常量清单 |
| P2 拆分实现 | ✅ | 20:45 | - | 主文件 910 行 + 3 子模块 + 15 re-export |
| P3 验证 + commit | ✅ | 21:15 | - | 64 passed + 606 passed 全量 + 三上下文冒烟 |
| P4 归档 + TD-365 更新 | ✅ | 21:18 | - | |

## Deviation Log

- D1: re-export 段位置 bug（追加在入口点后 → NameError）→ 修复为插入（N202 ⑰）
- D2: governance 上下文模块名循环（partial-init）→ 主文件头部无条件注册顶层名（N202 ⑱）
- D3: benchmark 1.05s 失败经基线对比确认抖动非回归

## 背景

- `scripts/bootstrap/sync_ai_memory.py` 1384 行（TD-365 阈值 1000）：35 顶层函数 + FrontMatterError + 15 常量。
- **调用契约（3 条，拆后必须全保持）**：
  1. CLI: `python scripts/bootstrap/sync_ai_memory.py [--query|--stats|...]`（project_rules/gaf_init 引用）
  2. importlib: `importlib.import_module('scripts.bootstrap.sync_ai_memory')`（test_doc_health_check.py d5 复用 frontmatter 校验）
  3. governance batch: `bootstrap.sync_ai_memory` import-based 调用
- **测试契约（N202 ① 检查）**：scripts/tests 以 sys.path hack `import sync_ai_memory` 方式导入，**模块属性 patch 2 个**：
  - `sync_ai_memory.yaml = ...`（test_sync_ai_memory.py）→ 影响 parse_front_matter/_rebuild_text
  - `sync_ai_memory.REPO_ROOT_DEFAULT = tmp_path`（test_sync_conflict.py）→ 影响 _check_source_conflict/_mark_conflict/_load_chroma_collection/query_semantic/update_sync_state/main

## P1 结构分析结论

6 功能域 + 调用图：

| 域 | 函数数 | 行数域 | 依赖 |
|----|-------|--------|------|
| frontmatter（留主文件） | 13 | L117-491 | 内部互调 + REPO_ROOT_DEFAULT/yaml patch 依赖 |
| collect | 7 | L501-707 | → frontmatter.parse_front_matter |
| semantic（留主文件） | 4 | L810-920 | REPO_ROOT_DEFAULT patch 依赖 |
| state（留主文件） | 2 | L921-1014 | REPO_ROOT_DEFAULT patch 依赖 |
| mtime_cache | 5 | L1015-1103 | 独立（无 patch 依赖，测试直接调函数） |
| counters | 3 | L1104-1212 | 独立 |
| main（留主文件） | 1 | L1213-1384 | 聚合全部 |

**patch 兼容决策**（N202 ⑯ 基线对比 + ① patch 点语义）：
- **2 个被 patch 模块属性（yaml / REPO_ROOT_DEFAULT）必须留在主文件**（测试 patch 主文件模块属性 → 函数在主文件内查找模块全局才生效；移出后 import-time 绑定值不变 → patch 失效，s35 反模式重演）。
- **依赖这 2 个属性的域（frontmatter/state/semantic）留主文件**（13+2+4 函数）。
- **collect/mtime_cache/counters（15 函数）移出**到 `scripts/bootstrap/ai_memory_sync/` 子包（3 模块）。
- 主文件：常量 15 + FrontMatterError + 19 函数 + main + `__all__`（15 移出函数 re-export）+ try 双路径 import 子模块（兼容 sys.path hack / 包导入两上下文）。
- collect 依赖 parse_front_matter：try 双路径 `_main` 绑定 + 运行时属性访问（函数对象共享 → 主文件内全局查找 → yaml patch 语义保持）。

主文件预估 ~820 行（< 1000 ✅）；移出 ~400 行。

## P2 拆分实现

- 脚本 `.trash/s38_split_sync_ai_memory.py`：按函数名清单切块（AST 定位函数边界），保留函数内注释。
- 子模块文件：
  - `ai_memory_sync/__init__.py`（空文档）
  - `ai_memory_sync/collect.py`：collect_lessons/_symptom_tokens/query_lessons/_scan_failure_modes_index/_scan_yn_matrices/_scan_summaries/query_all_sources
  - `ai_memory_sync/mtime_cache.py`：_cache_path/_build_mtime_manifest/_load_cache/_write_cache/_check_cache_valid（含 CACHE_FILE_NAME/CACHE_EXTERNAL_DEPS 常量搬入）
  - `ai_memory_sync/counters.py`：_sync_lessons_readme_count/_sync_yn_matrices_auto_updated/_sync_archived_count_in_rules
- 主文件尾部：try 双路径 import + 15 re-export（`collect_lessons = collect.collect_lessons` 等）→ main/测试直接调用名不变。
- 幂等：重跑前 `git checkout -- scripts/bootstrap/sync_ai_memory.py` + 删 ai_memory_sync/ 目录（N202 ⑪）。

## P3 验证

1. `python -m pytest scripts/tests/test_sync_ai_memory.py scripts/tests/test_sync_ai_memory_cache.py scripts/tests/test_sync_conflict.py scripts/tests/test_sync_lock.py -p no:django -o addopts=""`（4 个直接依赖文件全绿 = patch 契约保持）
2. `python -m pytest scripts/tests/ -p no:django -o addopts=""`（全量 scripts 测试，与基线一致）
3. 双上下文冒烟：`python scripts/bootstrap/sync_ai_memory.py --stats`（CLI）+ `from scripts.bootstrap import sync_ai_memory`（包导入）
4. `python -m ruff check scripts/bootstrap/` 0 errors
5. 基线对比：git checkout 还原后跑关键测试（N202 ⑯）

## P4 归档

- spec → archived/ + hash 回填；TD-365 更新 5/9；N202 lesson 追加（若新坑）；spec-context + N173 + evidence 三件套 + B2 + session

## 验收标准

- [ ] 主文件 < 1000 行，15 函数移出，35 函数契约完整（函数名/签名不变）
- [ ] 4 个直接依赖测试文件全绿（yaml/REPO_ROOT_DEFAULT patch 语义保持）
- [ ] scripts/tests 全量与基线一致
- [ ] CLI + importlib + governance batch 三调用路径冒烟通过
- [ ] ruff 0 errors