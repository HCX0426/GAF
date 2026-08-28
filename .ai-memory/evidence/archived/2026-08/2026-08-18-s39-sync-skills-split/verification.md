# s39 verification — sync_skills.py 拆分验证

## 验证矩阵

| # | 验证项 | 结果 | evidence |
|---|--------|------|----------|
| 1 | 主文件行数 | ✅ 457 行（1064 → 457，验收 < 550） | `wc -l sync_skills.py` |
| 2 | 依赖测试 | ✅ **25 passed** | test_decision_tree_sync (5) + test_sync_skills_timestamps (4) + test_sync_changelog (6) + test_bootstrap_gaf (10)，`pytest -p no:django -o addopts=""` |
| 3 | governance batch | ✅ **13/13 passed** | `python scripts/hooks/gaf_governance_batch.py`（含 sync_skills --check 子项） |
| 4 | 三上下文冒烟 | ✅ CLI `--check` rc 0；`from scripts.bootstrap import sync_skills` re-exports NONE missing（10 个抽查符号）；governance 等价 `import bootstrap.sync_skills` + main callable | 见下 |
| 5 | ruff | ✅ F401/I001/F841/F821 清零（27 fixed）；UP006/UP035/E402 预存风格保留（s38 同策略） | `ruff check --select F401,I001,F841,F821` |
| 6 | scripts 全量回归 | ✅ **580 passed + 2 skipped**（排除 test_e2e_run_all 环境性 5173 未启动 + test_layer_benchmark 已知抖动，与 s38 基线一致） | `pytest scripts/tests/ --ignore=...` |

## 三上下文冒烟详情

1. **CLI**：`python scripts/bootstrap/sync_skills.py --check` → rc 0，输出 "4 skills + 1 rule 副本一致"
2. **包导入**：`from scripts.bootstrap import sync_skills` → 抽查 10 个符号（check_l2_consistency/cmd_changelog/cmd_update_timestamps/append_changelog_entry/TIMESTAMP_SKILLS/DECISION_TREE_COPIES/_read_text/sync_skill/inspect_skill/REPO_ROOT_DEFAULT）全部可访问
3. **governance 等价**：`import bootstrap.sync_skills`（sys.path = [hooks, scripts]）→ main callable

## 失败修复记录（验证期）

- **D1**：constants.py `parents[2]` → `parents[3]`（CLI 报仓库无源文件）
- **D2**：changelog.py 补 `import re`；checks.py 补 `_read_text`；主文件补 `import hashlib`（NameError）
- **D3**：ruff --fix 删 re-export → 恢复 + `# noqa: F401`（测试 ImportError）
- **D4**：monkeypatch 目标改 skill_sync.constants + timestamps.py 改模块属性访问（测试断言失败）

## 时间

- N173：start 21:25 / end 22:15 / duration ~50min / within_baseline（大修改 < 60min 基线 ✅）/ root_cause：D1 parents 层级 + D2 import 补全 + D3 ruff 删 re-export + D4 monkeypatch 持有者
