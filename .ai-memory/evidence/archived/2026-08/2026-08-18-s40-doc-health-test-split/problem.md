# s40 problem — test_doc_health_check.py 1279 行拆分

## 触发

TD-365（i1_large_files，P2）：`scripts/tests/test_doc_health_check.py` 1279 行 > 1000 阈值（2026-08-17 monthly_health_check 扫描）。TD-365 最后一个可拆文件（test_agent/test_scheduler 已排除）。

## 症状

- 单文件 1279 行，9 个测试域混合（common/report/run_all + 7 维度 + integration/性能/回归）
- 每个维度区段自带局部 import（`from governance.check_dimensions import dX_...`）
- 外部耦合：`doc_health_patch.py._map_dimension_to_test_file`（7 维 → 单文件路径映射）+ `check_doc_path_drift.py` 白名单

## 影响范围

- 调用方：pytest 收集（scripts/tests/ 全树）、doc_health_patch.run_relevant_pytest（按维度跑测试）、check_doc_path_drift 白名单
- 契约：62 个测试全数保留（pytest 收集 = 文件匹配 test_*.py）

## 目标

- 主文件 1279 → 10 平铺文件（每个 < 300 行），源文件删除
- 零测试丢失（62 → 62）
- 外部耦合映射同步更新（doc_health_patch 每维度一文件 = 行为改进）