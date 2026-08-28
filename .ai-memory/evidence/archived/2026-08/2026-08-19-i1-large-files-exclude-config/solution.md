# s41 solution — i1_large_files exclude_files 配置

## 实现

1. **monthly_health_check.py `check_i1_large_files`**：
   - `exclude_files = cfg.get("exclude_files", [])`（默认空 = 现有行为不变）
   - 超阈值后、生成 Issue 前：`fnmatch.fnmatch(rel, pat)` 匹配排除（repo-relative posix 路径）
   - docstring Skips 段补充说明（含 TD-365 排除依据 -）
   - `import fnmatch` 已存在（无需新增）

2. **thresholds.yaml `monthly_checks.i1_large_files`**：
   ```yaml
   exclude_files:
     - "backend/gaf_ai/tests/test_agent.py"
     - "backend/scheduler/tests/test_scheduler.py"
   ```
   注释：有意保留大文件（TD-365 排除, 2026-08-04 有意合并 -, evidence 链接）

3. **测试** `test_i1_exclude_files_skips_deliberately_large`：2 个 2100 行文件 + exclude 1 个 → 断言仅 1 issue 且为未排除文件

## 关键决策

- **fnmatch 而非精确匹配**：支持未来模式排除（如 `backend/gaf_ai/tests/*`），与 d2_bloat per_file_thresholds 的 fnmatch 语义一致
- **默认空列表**：不配置 = 行为不变（向后兼容）
- **排除决策在配置层留痕**：thresholds.yaml 注释引用 evidence，AI/用户可见排除原因