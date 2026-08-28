# s38 problem statement — sync_ai_memory.py 1384 lines (TD-365)

## 问题

`scripts/bootstrap/sync_ai_memory.py` 1384 行（TD-365 大文件阈值 1000），35 顶层函数 + FrontMatterError + 15 常量混在一个文件。该文件是 GAF AI 记忆同步核心，被 3 条调用路径依赖：

1. CLI: `python scripts/bootstrap/sync_ai_memory.py [--query|--stats|...]`
2. importlib: `importlib.import_module('scripts.bootstrap.sync_ai_memory')`（test_doc_health_check d5）
3. governance batch: `bootstrap.sync_ai_memory` import-based（gaf_governance_batch CHECKS[1]）

## 拆分约束（N202 ① patch 点契约）

- 测试以 sys.path hack `import sync_ai_memory`（顶层模块名）导入，patch 2 个模块属性：
  - `sync_ai_memory.yaml`（test_sync_ai_memory.py）→ 影响 parse_front_matter/_rebuild_text
  - `sync_ai_memory.REPO_ROOT_DEFAULT`（test_sync_conflict.py）→ 影响 _check_source_conflict/_mark_conflict/_load_chroma_collection/query_semantic/update_sync_state/main
- 被 patch 的函数/域必须留在主文件（主文件内模块全局查找才生效，移出后 import-time 绑定值不变 → patch 失效，s35 反模式重演）

## 域划分

| 域 | 函数数 | 处理 |
|----|-------|------|
| frontmatter | 13 | 留主文件（yaml patch 依赖） |
| collect | 7 | 移出 → ai_memory_sync/collect.py |
| semantic | 4 | 留主文件（REPO_ROOT_DEFAULT patch 依赖） |
| state | 2 | 留主文件（REPO_ROOT_DEFAULT patch 依赖） |
| mtime_cache | 5 | 移出 → ai_memory_sync/mtime_cache.py |
| counters | 3 | 移出 → ai_memory_sync/counters.py |
| main | 1 | 留主文件 |

目标：主文件 1384 → < 1000 行；移出 15 函数到 `scripts/bootstrap/ai_memory_sync/` 子包。