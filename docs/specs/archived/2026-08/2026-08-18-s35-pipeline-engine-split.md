# s35 — agent/src/engine/pipeline_engine.py 拆分 (2121 行 → mixin 模块)

> **类型**: refactor (大文件拆分, TD-365 第二批) | **日期**: 2026-08-18 | **来源**: 用户"继续，循环任务" → TD-365 接修 (agent 层最大文件)
> **状态**: ✅ 已归档 → `docs/specs/archived/2026-08/2026-08-18-s35-pipeline-engine-split.md`
> **关联**: TD-365 / s34 (views.py 拆分先例, 方法论复用)
> **实现 commit**: `-`

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit hash | 验收 evidence |
|------|------|---------|------------|--------------|
| Phase 1 拆 pipeline_models/utils + 4 mixin + 主类 re-export | ✅ | 2026-08-18 | - | 7 个模块: 主 51 行; execution 666 / lifecycle 454 / node_execution 579 / recovery 267 / models 35 / utils 169 (全部 < 700) |
| Phase 2 验证 (agent 测试 + ruff + 副作用 import 验证) | ✅ | 2026-08-18 | — | agent 全量 2305 passed / 3 skipped; ruff 2 预存 (B905/SIM105, 原文件已有); PIPELINE_NODE_REGISTRY 41 节点注册验证 ✓ |
| Phase 3 commit + 归档 + TD-365 更新 | ✅ | 2026-08-18 | - | pre-commit 全过; spec 已归档; TD-365 pipeline_engine.py ✅ 已拆 |

## 背景与根因

**现象**: monthly_health_check i1_large_files 报 `agent/src/engine/pipeline_engine.py` 2121 行 (>2000 阈值)。TD-365 登记 (2026-08-17)。

**根因**: PipelineEngine 单巨类 1890 行 (40 个方法), 功能迭代持续追加, 无拆分治理。

**拆分决策依据 (N151)**:
- 顶层结构: `_truncate_dict` (L49) / `_truncate_result_data_priority` (L95) / `PipelineResult` (L205) / `PipelineEngine` (L232-2121)
- PipelineState/StepState 从 engine.context import (非本文件定义); MAX_STEP_TIMEOUT 模块级常量 (L46)
- 引用方: `engine/__init__.py` (PipelineEngine/PipelineResult/MAX_STEP_TIMEOUT) + executor.py:82 / orchestrator.py:720 / nodes/sub_pipeline.py:152 (懒加载) + 9 个测试文件 import PipelineEngine/PipelineResult/PipelineState/MAX_STEP_TIMEOUT/_truncate_result_data_priority
- **关键副作用**: L22 `import engine.nodes` (注册 PIPELINE_NODE_REGISTRY) — 必须保留在主 re-export 文件, 任何 `import engine.pipeline_engine` 都触发注册
- **方案 A (选定)**: mixin 模式 — PipelineEngine 方法按功能域拆 4 个 mixin (lifecycle/execution/node_execution/recovery), 主类继承 mixin 保持 API 不变 → 引用方零改动
- 方案 B (仅拆 helper + 保留巨类) / C (KEEP) 拒绝: B 收益不足, C 违反技术债不堆积

**排除项**: 不拆 execute 单方法内部逻辑 (629 行, 纯移动零变更原则; 拆方法内部 = 行为变更高风险); execute 所在 mixin ~630 行略超 600, 记录 deviation

## Phase 1 详细任务

| 模块 | 内容 | 估算行数 |
|------|------|---------|
| `engine/pipeline_models.py` | PipelineResult (L205-231) | ~30 |
| `engine/pipeline_utils.py` | _truncate_dict + _truncate_result_data_priority + MAX_STEP_TIMEOUT | ~160 |
| `engine/pipeline_lifecycle.py` | PipelineSetupMixin (init/setters/load/validate/properties, L243-616) + PipelineControlMixin (pause/resume/cancel/skip/get_state, L2062-2121) | ~480 |
| `engine/pipeline_execution.py` | PipelineExecutionMixin (execute, L618-1246) | ~630 |
| `engine/pipeline_node_execution.py` | PipelineNodeExecutionMixin (_execute_node_step/retry/fallback/logs/lifecycle/safe_delay/wait_freezes, L1251-1810) | ~560 |
| `engine/pipeline_recovery.py` | PipelineRecoveryMixin (_attempt_recovery/_resolve_next_node/loop, L1812-2060) | ~250 |
| `engine/pipeline_engine.py` | 主类 `class PipelineEngine(PipelineSetupMixin, PipelineExecutionMixin, PipelineNodeExecutionMixin, PipelineRecoveryMixin)` + 副作用 import engine.nodes + re-export (PipelineResult/MAX_STEP_TIMEOUT/_truncate_*) | ~50 |

`pipeline_engine.py` 保留 re-export (`__all__` + 全部符号), 引用方零改动。

## 验收标准

1. `agent/src/engine/pipeline_engine.py` 行数 < 100 (mixin 继承 + re-export); 各 mixin 模块 < 700 行
2. `import engine.pipeline_engine` 后 PIPELINE_NODE_REGISTRY 非空 (副作用 import 保留)
3. 引用方零改动: engine/__init__.py / executor.py / orchestrator.py / sub_pipeline.py 不报 ImportError
4. agent 相关 pytest 全绿 (test_pipeline_engine.py / test_engine_*.py 等, `-p no:django -o addopts=""`)
5. 无行为变更 (纯移动 + mixin 继承, 零逻辑改动); ruff 无新增错误

## 已知限制

- execute 单方法 629 行不拆 (纯移动原则); pipeline_execution.py 666 行略超 600 估算 (deviation log 记录)
- 不处理 TD-365 其余 6 个文件 (device.py / models.ts / scripts 3 个 / test_agent / test_scheduler 已排除)

## Deviation Log

| # | 偏离 | 原因 | 处理 |
|---|------|------|------|
| 1 | execute 所在 mixin 666 行 (> 600 估算) | 单方法 execute 629 行不拆 (零变更原则) | 验收标准为 < 700, 666 达标; 记录在已知限制 |
| 2 | 新增 `_get_structured_logger` 转发函数 (pipeline_execution.py) | 测试 patch `engine.pipeline_engine.get_structured_logger` 模块属性注入 fake logger; execute 移出后模块级查找不再指向 patch 点 | 转发函数运行时查 `engine.pipeline_engine` 属性, 保持测试 patch 语义; 非行为变更 (同一函数对象) |
| 3 | 主文件 __all__ 扩展 3 符号 (PipelineValidator / get_structured_logger / PipelineState) | 测试 `from engine.pipeline_engine import X` 契约 (conftest + 4 测试); ruff --fix 会清未在 __all__ 的 re-export | 全部符号入 __all__ + 脚本同步 |
| 4 | 脚本 header 过滤 2 次 bug (drop 吞 import 块 / set 匹配误删 L30) | 迭代修复 | 最终脚本顺序块匹配, 可重跑 |

## 实施产物

- 拆分脚本: `.trash/s35_split_pipeline.py` (AST 精确边界 + mixin 分组 + 转发函数 + 主类构造, 可重跑)
- 拆分结果: 7 个模块 (见阶段状态表行数)
- 测试: agent 全量 2305 passed / 3 skipped (`-p no:django -o addopts=""`)