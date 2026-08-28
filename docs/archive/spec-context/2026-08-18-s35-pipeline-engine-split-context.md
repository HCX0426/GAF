# s35 — pipeline_engine.py 拆分 — spec-context 承载体

> spec: docs/specs/archived/2026-08/2026-08-18-s35-pipeline-engine-split.md
> 创建: 2026-08-18 (B2 大修改, TD-342 强制)

## N173 用时字段

- start_ts: 2026-08-18T19:20:00+08:00 (s35 拆分脚本首跑前)
- end_ts: 2026-08-18T21:22:00+08:00 (commit -)
- duration_min: 122
- within_baseline: false (大修改基线 <60min)
- root_cause_if_over: 拆分脚本 6 轮迭代调试 (header drop 吞 import / set 匹配误伤 / 装饰器丢失 / @dataclass 丢失 / re-export F401 被删 / patch 点转发), 每轮全量验证 (~3min/轮); 其中 ~35min 为契约发现 (测试 import + patch 语义分析) + 5 处预存空 except 修复 (N150 当场处理, ~10min)

## 1. 用户决策原文

- 用户 "继续，循环任务"（强触发 = 循环模式, 连续接修 TD-365）。
- 用户历史要求（沉淀于 project_rules §4.8/§0）："做项目要考虑全面的，不要遗留技术债务" + "技术债务延后 = 做完上一个类别接着做" → TD-365 拆分治理为当前任务 (s34 → s35 → 后续)。

## 2. N151 5 步法评估过程

1. **架构盘点**: `agent/src/engine/pipeline_engine.py` 2121 行, 顶层 4 定义 (2 helper + PipelineResult + PipelineEngine 巨类 1890 行/40 方法); 引用方: engine/__init__.py (3 符号) + executor.py:82 / orchestrator.py:720 / sub_pipeline.py:152 (懒加载) + 9 测试文件; 关键副作用: L22 `import engine.nodes` 注册 PIPELINE_NODE_REGISTRY。
2. **识别反模式**: 单巨类无限膨胀 (功能迭代持续追加, 无拆分治理); 无双套并存。
3. **A/B/C 备选**:
   - **A (选定)**: mixin 模式 — 4 个功能域 mixin (lifecycle/execution/node_execution/recovery) + models/utils 外迁, 主类继承保持 API 不变 → 引用方零改动
   - B: 仅拆 helper 保留巨类 → 收益不足 (class 主体仍 >1800 行)
   - C: KEEP → 违反技术债不堆积原则 (N151 拒绝路径)
4. **拒绝反模式**: B (收益不足) / C (KEEP) 均拒绝; mixin 方案无行为变更风险 (纯移动 + 继承)。
5. **AI 自决边界**: mixin 分组边界自决; execute 单方法 629 行不拆 (零变更原则); 主文件 __all__ 契约符号自决。

## 3. N167 七维度评分

| 维度 | 评分 | 理由 |
|------|------|------|
| 1 架构长远性 | 9 | 功能域内聚, 后续迭代按域扩展 (与 s34 view_sets 同构) |
| 2 全局归一化 | 8 | 与 s34 拆分模式一致, re-export + __all__ 归一 |
| 3 新旧兼容 | 9 | 引用方零改动 + 测试契约全保持 (2305 passed) |
| 4 现有业务完善 | 7 | 零逻辑变更; 2 处预存 ruff 错误 (B905/SIM105) 保持不动 |
| 5 性能资源优化 | 7 | 模块加载等价 (mixin import 链无循环) |
| 6 安全合规加固 | 6 | 无敏感面变化 |
| 7 长期维护成本 | 9 | 单文件 2121 → 最大模块 666; 定位/审查成本大降 |
| **总分** | **55/63** | ≥19 且领先 B/C ≥5 → AI 自决 ✓ |

## 4. 关键实施决策 (process 小坑 + 修复方法)

1. **AST 边界两坑**: ① `m.lineno` 丢装饰器行 → 静态方法无 @staticmethod → ruff N805; 修复 decorator_list[0].lineno (s34 教训复用)。② models 区间丢 @dataclass → TypeError: PipelineResult() takes no arguments → 同修复。
2. **header 过滤两 bug**: ① drop 循环只在空行退出, import 行被吞 → 113 F821; 修复遇非注释行退出。② set 匹配删 get_logger 块误伤同字符串 L30 (StructuredLogger 块) → 语法错; 修复顺序块匹配。
3. **ruff F401 删 re-export**: 主文件 header 全量 import 被 --fix 清 (类体空, 全 unused) → 测试 `from engine.pipeline_engine import PipelineState/get_structured_logger/PipelineValidator` 断 → 修复: 公共契约符号入 __all__ (ruff 对 __all__ 名字不报 F401)。
4. **patch 点失效 (最重要, 非 s34 先例)**: 测试 `engine_mod.get_structured_logger = lambda...` patch 模块属性注入 fake logger; execute 移出 pipeline_engine.py 后, pipeline_execution 模块级查找不再指向 patch 点 → 12 个 JSONL 测试空事件。修复: `_get_structured_logger` 转发函数运行时 `from engine import pipeline_engine` 查属性 — 保持测试 patch 语义, 运行时同一函数对象 (无行为变更)。
5. **E402 规避**: logger 统一放所有 imports 之后 (mixin header 裁剪 + EXTRA_IMPORTS 顺序), ruff --fix 不修多行 E402 (s34 教训)。
6. **脚本可重跑性**: git checkout 恢复源文件 → 跑脚本 → ruff --fix; 脚本含 GROUPS/EXTRA_IMPORTS/EXTRA_CODE/__all__ 全参数化, 未来拆分复用 (s34/s35 两轮 8 坑全在脚本里规避)。
7. **预存错误零变更**: B905 (zip strict) / SIM105 (suppress) 原文件已有, 不动。

## 5. 反思 (N193 任务归属复查)

- 拆分中发现的问题全部当场处理: 转发函数 ✓ / __all__ 契约 ✓ / 装饰器 ✓ / @dataclass ✓
- 无遗留建议; execute 666 行偏离已记录到 spec deviation log (验收 <700 达标)
- 新发现: 测试对 `engine.pipeline_engine` 模块属性的 patch 语义是隐式契约 — 已在 solution.md 记录, 未来拆分任何文件前先 grep 测试 patch 点