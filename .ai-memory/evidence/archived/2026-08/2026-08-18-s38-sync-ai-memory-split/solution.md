# s38 solution — domain module split with module-name registration

## 方案

- 主文件保留：常量 15 + FrontMatterError + frontmatter 13 + state 2 + semantic 4 + main ≈ 910 行（< 1000 ✅）+ 15 个 re-export 绑定（`collect_lessons = collect.collect_lessons` 等，保持 main/测试直接调用名不变）+ try 双路径 import 子模块。
- 移出 3 个独立域（无 patch 依赖）到 `scripts/bootstrap/ai_memory_sync/` 包：
  - `collect.py`（296 行）：collect_lessons / _symptom_tokens / query_lessons / _scan_failure_modes_index / _scan_yn_matrices / _scan_summaries / query_all_sources（含 EXTENDED_SCAN_PATHS 死常量）+ 注释
  - `mtime_cache.py`（97 行）：_cache_path / _build_mtime_manifest / _load_cache / _write_cache / _check_cache_valid（含 CACHE_FILE_NAME / CACHE_EXTERNAL_DEPS）
  - `counters.py`（107 行）：_sync_lessons_readme_count / _sync_yn_matrices_auto_updated / _sync_archived_count_in_rules
  - `__init__.py`：docstring
- collect.py 对主文件的依赖（parse_front_matter / FrontMatterError）经 `_main` 运行时属性访问（函数对象共享 → 主文件内全局查找 → yaml patch 语义保持）。
- 拆分脚本：`.trash/s38_split_sync_ai_memory.py`（AST 行号切块 + 行号区间删除 + re-export 段插入）。

## D1 — re-export 段位置（N202 ⑰）

**现象**：CLI `--stats` 报 `NameError: name '_sync_lessons_readme_count' is not defined`；runpy 模拟成功、直接 CLI 失败。

**根因**：拆脚本把 re-export 段**追加到文件末尾**，但原文件末尾本来就是 `if __name__ == "__main__": sys.exit(main())` → main() 先执行，re-export 绑定永远未执行。import 上下文测试不触发 __main__ 路径，全量回归 CLI 才暴露。

**修复**：拆脚本改为把 re-export 段**插入**到入口点块之前（`new_text.rfind('\n\nif __name__ == "__main__":')` 定位插入点）。

## D2 — 多模块名上下文循环 + 顶层包名冲突（N202 ⑱）

**现象**：governance 冒烟（`importlib.import_module('bootstrap.sync_ai_memory')`）报 `AttributeError: partially initialized module ... has no attribute 'collect_lessons'`；sys.path hack 测试通过但 governance 失败；直接跑 governance batch 报 `No module named 'ai_memory_sync'`。

**根因（两层）**：
1. **循环**：同一文件以 4 种模块名加载（__main__ / scripts.bootstrap.sync_ai_memory / bootstrap.sync_ai_memory / 顶层 sync_ai_memory）。collect.py 只检查 `"sync_ai_memory" in sys.modules`（顶层名）→ governance 上下文顶层名不存在 → else 分支 `from scripts.bootstrap import sync_ai_memory as _main` 触发**第二个 module 对象**加载 → 该对象 re-export 时 collect 还在 partial 初始化 → AttributeError 循环。
2. **真根因（win32/scripts 冲突）**：主文件尾部 `from scripts.bootstrap.ai_memory_sync import` 依赖顶层 `scripts` 包，但 sys.path 里的 `D:\code\GAF\scripts` 条目是给 `import bootstrap`（子目录包）用的——governance 环境（file-run，sys.path 无 cwd）`import scripts` 按 sys.path 扫描：index 0 hooks（无）→ index 1 D:\code\GAF\scripts（**该目录内无 scripts 子目录**）→ ... → index 9 `site-packages\win32`（**pywin32 的 scripts 目录，namespace 包，同名冲突**）→ 命中 win32/scripts → `from scripts.bootstrap` → ModuleNotFoundError → except 分支 `from ai_memory_sync` 也失败（scripts/bootstrap/ 不在 path）。-c 模式成功是因为 sys.path 有 `''`（cwd = repo root）→ index 2 命中 D:\code\GAF\scripts。
   **判定方法**：单路径探测 `importlib.machinery.PathFinder.find_spec('scripts', [p])` 逐条 sys.path + 打印 `import scripts; scripts.__path__`。

**修复（两层）**：
1. 主文件头部**无条件**注册：`sys.modules.setdefault("sync_ai_memory", sys.modules[__name__])` → 任何上下文 collect 都绑定同一对象，永不二次加载。
2. 主文件尾部改用 `from bootstrap.ai_memory_sync import collect, counters, mtime_cache`（scripts/ 在 sys.path 时 bootstrap 子包直接可用，**不依赖顶层 scripts 包**，规避 win32/scripts 冲突）。

验证：4 种上下文（CLI / scripts.bootstrap 包导入 / governance bootstrap 包导入 / sys.path hack 测试）全部通过；governance batch 13/13。

## D3 — 环境性测试失败甄别（非拆分引入）

scripts 全量 1 个失败 `test_layer_benchmark::test_l1_query_under_target`（1.05s vs 1.0s 阈值）：stash 还原主文件后**同样失败** → 边缘值抖动（subprocess 冷启动），非拆分回归。test_e2e_run_all 失败为前端 5173 未启动的环境依赖（预存）。