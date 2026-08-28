# Solution — s35 pipeline_engine.py 拆分 (2026-08-18)

## 方案
方案 A (mixin 拆分, N151 选定): PipelineEngine 方法按功能域拆 4 个 mixin, 主类继承保持 API 不变。

## 拆分结果 (7 模块)

| 模块 | 行数 | 内容 |
|------|------|------|
| `pipeline_models.py` | 35 | `@dataclass PipelineResult` (含 `__bool__`) |
| `pipeline_utils.py` | 169 | `_truncate_dict` + `_truncate_result_data_priority` + `MAX_STEP_TIMEOUT` |
| `pipeline_lifecycle.py` | 454 | PipelineSetupMixin (__init__/setters/load/validate/properties/control: pause/resume/cancel/skip/get_state) |
| `pipeline_execution.py` | 666 | PipelineExecutionMixin (execute 629 行单方法) + `_get_structured_logger` 转发 |
| `pipeline_node_execution.py` | 579 | PipelineNodeExecutionMixin (_execute_node_step/retry/fallback/logs/safe_delay/wait_freezes) |
| `pipeline_recovery.py` | 267 | PipelineRecoveryMixin (_attempt_recovery/_resolve_next_node/loop) |
| `pipeline_engine.py` | 51 | 主类继承 4 mixin + engine.nodes 副作用 + re-export (__all__ 8 符号) |

## 关键实施决策

1. **AST 精确边界**: `end_lineno` + `decorator_list[0].lineno` (装饰器行 — s34 教训: 静态方法装饰器丢失会导致 N805)
2. **副作用 import 保留**: 主文件 L15 `import engine.nodes  # noqa: F401` + 完整注释块
3. **re-export 契约**: `__all__` 8 符号 (PipelineEngine/PipelineResult/MAX_STEP_TIMEOUT/_truncate_dict/_truncate_result_data_priority/PipelineValidator/get_structured_logger/PipelineState) — 测试 `from engine.pipeline_engine import X` 依赖; 必须入 __all__ 防 ruff F401 误删
4. **patch 点转发**: `_get_structured_logger` 运行时查 `engine.pipeline_engine` 属性 (测试 patch 注入 fake logger 的语义保持)
5. **E402 规避**: logger 统一放所有 imports 之后 (mixin header 裁剪 + EXTRA_IMPORTS 顺序)
6. **header 裁剪**: 仅 mixin 文件剔除 engine.nodes 注释块 (顺序块匹配, set 匹配会误伤同前缀 L30) + get_logger import 块
7. **预存错误不动**: B905 (zip strict) / SIM105 (suppress) 原文件已有, 零变更原则保留

## 拆分脚本
`.trash/s35_split_pipeline.py` — 可重跑 (git checkout 源文件 → 跑脚本 → ruff --fix)。GROUPS 分组 + EXTRA_IMPORTS + EXTRA_CODE + 主类构造 + __all__ 全部参数化。