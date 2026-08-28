# s41 problem — i1_large_files 维度仍报 2 个已排除文件

## 触发

TD-365 闭环复核（s40 后跑 `monthly_health_check --root .` 验证 i1_large_files 报 0）→ 仍报 2 issues：test_agent.py (2434) + test_scheduler.py (2885)。

## 症状

- i1_large_files 维度报 2 个文件，但两者是 2026-08-04 有意合并排除的（-, evidence: 2026-08-04-test-file-merge/）
- health check 维度**无排除机制**（只有 skip_dir_parts / generated 过滤），排除决策只存在于文档层
- TD-365 验证标准 = "monthly_health_check i1_large_files 报 0" → 无法达成

## 影响范围

- monthly_health_check.py (check_i1_large_files) + thresholds.yaml (monthly_checks.i1_large_files) + test_monthly_health_check.py

## 目标

- i1_large_files 支持 exclude_files 配置（fnmatch 相对路径匹配）
- thresholds.yaml 登记 2 个排除文件（含排除原因注释）
- 维度报 0 → TD-365 验证标准达成