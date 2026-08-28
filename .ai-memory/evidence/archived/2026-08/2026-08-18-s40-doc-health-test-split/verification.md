# s40 verification — 测试文件拆分验证

## 验证矩阵

| # | 验证项 | 结果 | evidence |
|---|--------|------|----------|
| 1 | 测试迁移完整性 | ✅ **62 passed**（10 新文件；原 1279 行文件 62 test 全数：common 10 + d2 4 + d3 7 + d4 13 + d5 4 + d7 11 + d8 3 + d1 3 + d6 4 + integration 3） | `pytest scripts/tests/test_doc_health_*.py -p no:django -o addopts=""` |
| 2 | 外部耦合回归 | ✅ **35 passed**（test_doc_health_patch 20 — 含 _map_dimension_to_test_file 映射；test_doc_health_consumed 15） | `pytest test_doc_health_patch.py test_doc_health_consumed.py` |
| 3 | scripts 全量回归 | ✅ **580 passed + 2 skipped**（排除 test_e2e_run_all 环境性 5173 未启动 + test_layer_benchmark 抖动；与 s39 基线一致） | `pytest scripts/tests/ --ignore=...` |
| 4 | governance batch | ✅ **13/13 passed** | `python scripts/hooks/gaf_governance_batch.py` |
| 5 | ruff | ✅ F401 清零（1 fixed = d2 预存 tempfile） | `ruff check --select F401` |
| 6 | 文件规模 | ✅ 10 文件全部 < 300 行（54-284），源文件 1279 行删除 | `Get-ChildItem scripts/tests/test_doc_health_*.py` |

## 失败修复记录（验证期）

- **D1**：common 切块 (1,165)/(3,165) → (21,165)（future import 重复 SyntaxError）
- **D2**：源文件删除后脚本不可重跑 → `git checkout --` 恢复再拆
- **D3**：d2 区段预存 tempfile F401 → ruff --fix

## 时间

- N173：start 22:30 / end 23:15 / duration ~45min / within_baseline（大修改 < 60min 基线 ✅）/ root_cause：D1 切块点 + D2 幂等性 + D3 预存 F401