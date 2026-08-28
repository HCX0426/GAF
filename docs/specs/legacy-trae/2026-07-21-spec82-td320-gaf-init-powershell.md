---
spec_id: spec-82
title: TD-320 — gaf_init.ps1 PowerShell 等价版本
created: 2026-07-21
status: ✅ done
commit: -
related_td: [TD-320]
related_n: []
depends_on: []
blocks: [TD-328]
priority: P1
size: 中 (跨平台脚本翻译, ~300 行)
---

# spec-82: TD-320 — gaf_init.ps1 PowerShell 等价版本

## 背景与问题

`scripts/gaf_init.sh` 是 bash-only 脚本 (`#!/bin/bash`, `[[ ]]` / `source activate` / `wc -l` / `awk`)，Windows PowerShell 7.x 默认环境下不可直接运行。用户在 Windows 默认使用 PowerShell 7.x，每次开工需切到 git bash，影响开发体验。

## 修复方案 (方案 A: .ps1 + 保留 .sh)

创建 `scripts/gaf_init.ps1` 作为 PowerShell 等价版本，保留 `gaf_init.sh` 给 Linux/macOS。两个版本功能等价：

- 同样的 args: `--fast` (默认) / `--full`
- 同样的步骤: 0.UTF-8 / 1.conda / 2.dep check / 3.FULL-ONLY BLOCK (pre-commit install + sync_ai_memory + sync_skills + sync_session_context + build_memory_index + 5 skills 校验 + docs-index stale check + doc_health_check + L2 file 校验) / 3.7.L1 hard-load / 3.7.1.L2 量化 / P5 / 4.evidence / 5.entry hint / 6.session active / 7.final summary

## 实施清单

- [x] 创建 `scripts/gaf_init.ps1` (~300 行)
- [x] PowerShell 7.x 语法兼容 (使用 `$PSVersionTable.PSVersion.Major -ge 7` 验证)
- [x] 等价功能: `--fast` / `--full` 双模式
- [x] 错误处理: `$ErrorActionPreference = "Stop"` + `try/catch` 替代 `set -e`
- [x] UTF-8 强制: `$env:PYTHONIOENCODING = "utf-8"` + `$env:LC_ALL = "C.UTF-8"`
- [x] conda 激活: `conda activate gaf` (PowerShell 原生支持)
- [x] L1 hard-load 硬约束: `failure-modes.md` 不存在或 N## < 5 时 exit 1
- [x] 跑 `pwsh scripts/gaf_init.ps1 --fast` 验证 (< 1s)
- [x] 跑 `pwsh scripts/gaf_init.ps1 --full` 验证 (< 5s)
- [x] README.md 增加 PowerShell 入口说明 (L70+ 启动段)

## 验证标准

1. `pwsh scripts/gaf_init.ps1 --fast` 在 Windows PowerShell 7.x 直接运行 (无需 git bash)
2. 输出与 `bash scripts/gaf_init.sh --fast` 等价 (相同 7 步骤 + ✅ 标记)
3. `pwsh scripts/gaf_init.ps1 --full` 完整执行 pre-commit install + sync_ai_memory + sync_skills + L2 校验
4. L1 硬加载失败时 exit 1 (与 .sh 一致)
5. 保留 `gaf_init.sh` 不动 (Linux/macOS 仍可用)

## 关联文件

- `scripts/gaf_init.ps1` (新建)
- `scripts/gaf_init.sh` (保留不动)
- `README.md` (增加 PowerShell 入口说明)

## N176 hash 回填

本 spec 完成后 commit hash 立即回填到此 frontmatter (TD-303 N176 规则)。
