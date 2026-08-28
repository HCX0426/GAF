---
verification_type: pytest + manual
status: pass
---

- `pytest scripts/tests/test_check_claimed_rules.py` — 17 passed (N/A 语义 / 复盘触发判定 / 幂等标记 / 6/7 列兼容)
- 手动 `check_claimed_rules.py --no-record` — 输出复盘触发警告 (- 0% / - 40% / - 0%)
- ruff check 2 文件 — All checks passed
- pre-commit 全链 — 通过 (除预存 evidence 目录, 本次已补全)
- 预存 18 测试失败已确证与本次改动无关 (stash 前后相同), 登记 TD-363

## TD-363 修复验证 (2026-08-16)

- `pytest scripts/tests/` 全量 — **562 passed, 2 skipped, 31 deselected** (49.6s) — 原 18 failed / 575 passed 全部消除
- 逐类复跑: probe_unknown_task 10 passed / extract_lessons 4 passed / gaf_commit_wrapper 4 passed / layer_benchmark 11 passed (复跑 2 次稳定) / e2e_run_all 16 passed + 1 browser 场景需前端 (默认 -m "not e2e" 跳过, 31 deselected)
- 根因修复验证: pyproject `markexpr` 改 `addopts = ["-m", "not e2e"]` 后 `-m "not e2e"` 显式跑同文件 17 deselected (此前 markexpr 静默不生效, e2e 从未被跳过)
- TD-363 段落已从 active-tech-debt.md 剪切至 fixed-tech-debt.md (§4.5), 索引表手动补行 (sync 脚本仅归档时重建)
