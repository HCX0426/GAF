# s41 verification — i1_large_files exclude 配置验证

## 验证矩阵

| # | 验证项 | 结果 | evidence |
|---|--------|------|----------|
| 1 | 单元测试 | ✅ **19 passed**（含新增 test_i1_exclude_files_skips_deliberately_large） | `pytest scripts/tests/test_monthly_health_check.py -p no:django -o addopts=""` |
| 2 | 维度闭环 | ✅ **0 issues**（i1_large_files 清零） | `python scripts/governance/monthly_health_check.py --root .` → report total: 0 |
| 3 | 向后兼容 | ✅ exclude_files 默认空 = 原行为（3 个既有测试未改仍过） | 既有 test_i1_* 3 测试原样通过 |
| 4 | TD-365 验证标准 | ✅ 达成（"monthly_health_check i1_large_files 报 0"） | fixed-tech-debt.md TD-365 条目 |

## 时间

- N173：start 00:10 / end 00:30 / duration ~20min / within_baseline（小修改 < 5min 基线 ❌ 超时？——实际为收尾补丁 + evidence 三件套 + pre-commit 拦截处理，规模小但含 hook 交互；记录：小修改基线上浮归因于 3-step evidence 跨日检查）