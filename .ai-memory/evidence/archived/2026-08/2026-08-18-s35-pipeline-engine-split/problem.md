# Problem — s35 pipeline_engine.py 拆分 (2026-08-18)

## 现象
monthly_health_check i1_large_files 报 `agent/src/engine/pipeline_engine.py` 2121 行 (>2000 阈值)。TD-365 登记 (2026-08-17)。

## 根因
PipelineEngine 单巨类 1890 行 (40 个方法), 功能迭代持续追加, 无拆分治理。顶层仅 4 个定义: `_truncate_dict` (L49) / `_truncate_result_data_priority` (L95) / `PipelineResult` (L205) / `PipelineEngine` (L232-2121)。

## 影响
- 单文件难导航 (40 方法混 6 个功能域: lifecycle/execution/node_execution/recovery/control)
- 修改时上下文窗口压力 (单文件读全量才能改)
- 与 s34 (views.py 拆分) 同根因: 大文件治理缺失

## 关键约束
- L22 `import engine.nodes` 副作用 (注册 PIPELINE_NODE_REGISTRY) 必须保留在主文件
- 引用方零改动: engine/__init__.py / executor.py:82 / orchestrator.py:720 / sub_pipeline.py:152 (懒加载)
- 测试契约: conftest + 测试 import `engine.pipeline_engine` 的 PipelineEngine/PipelineResult/PipelineState/MAX_STEP_TIMEOUT/_truncate_result_data_priority/get_structured_logger/PipelineValidator
- 测试 patch `engine.pipeline_engine.get_structured_logger` 模块属性注入 fake logger