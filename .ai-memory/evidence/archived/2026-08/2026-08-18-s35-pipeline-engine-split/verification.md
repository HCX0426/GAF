# Verification — s35 pipeline_engine.py 拆分 (2026-08-18)

## 验收标准逐项验证

| # | 验收标准 | 结果 | Evidence |
|---|---------|------|----------|
| 1 | pipeline_engine.py < 100 行; mixin 各 < 700 行 | ✅ | 主 51 / execution 666 / lifecycle 454 / node_execution 579 / recovery 267 / models 35 / utils 169 |
| 2 | `import engine.pipeline_engine` 后 PIPELINE_NODE_REGISTRY 非空 | ✅ | 冒烟脚本: registry 41 nodes (PIPELINE_NODE_REGISTRY len 41) |
| 3 | 引用方零改动, 不报 ImportError | ✅ | agent 全量测试含 orchestrator/executor/sub_pipeline 路径 2305 passed |
| 4 | agent 相关 pytest 全绿 | ✅ | `python -m pytest agent/tests/ -p no:django -o addopts=""`: **2305 passed, 3 skipped** (171.86s) |
| 5 | 无行为变更; ruff 无新增错误 | ✅ | ruff: 2 errors 全为预存 (B905 zip strict L91 recovery / SIM105 suppress L182 execution — 原文件已有); 拆分引入的 N805/F821/E402 全部清零 |

## 中间问题与修复 (迭代记录)

1. **header drop 循环吞 import 块** (L23-40) → 113 F821 → 修复: drop 遇到非注释行退出
2. **装饰器行丢失** → 3 N805 (静态方法无 @staticmethod) → 修复: method_bounds 用 decorator_list[0].lineno
3. **models 丢 @dataclass** → TypeError: PipelineResult() takes no arguments → 修复: pr_start 用 decorator 行
4. **re-export 被 ruff F401 删** (get_structured_logger/PipelineValidator/PipelineState) → 测试 ImportError → 修复: __all__ 8 符号
5. **patch 点失效** (execute 移出 pipeline_engine) → 12 JSONL 测试失败 → 修复: `_get_structured_logger` 转发函数
6. **set 匹配误删 L30** (与 L35 同字符串) → 语法错 → 修复: 顺序块匹配

## 方法级完整性
- 方法对比: old 40 (含 PipelineResult.__bool__) vs new 39 (engine 方法全在, __bool__ 随 models 迁移) — 零丢失
- 行为零变更: 全部为纯移动 (AST 边界复制), 唯一代码改点 = _get_structured_logger 调用替换 (运行时同一函数对象)