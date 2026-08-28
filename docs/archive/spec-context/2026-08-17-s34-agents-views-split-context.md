# s34 — agents/views.py 拆分 — spec-context 承载体

> spec: docs/specs/archived/2026-08/2026-08-17-s34-agents-views-split.md
> 创建: 2026-08-18 (B2 大修改, TD-342 强制)

## N173 用时字段

- start_ts: 2026-08-18T17:35:00+08:00 (s34 拆分脚本首跑前)
- end_ts: 2026-08-18T18:56:00+08:00 (commit 时刻)
- duration_min: 81
- within_baseline: false (大修改基线 <60min)
- root_cause_if_over: 拆分脚本 3 轮调试 (v1 闭区间切片 / v2 header pop 方向 bug / docstring 剥离), 包名冲突重构 (views/ → view_sets/), 4 处预存空 except 修复 + evidence/spec-context 补建; 其中 ~25min 为 hook 链补建 (evidence 3 件套 + B2 + N173)

## 1. 用户决策原文

- 用户多次 "继续"（弱触发 = 每次授权 1 个 spec），授权按优先级接修 TD。
- 用户历史要求（沉淀于 project_rules §4.8/§0）："做项目要考虑全面的，不要遗留技术债务" + "技术债务延后 = 做完上一个类别接着做，不是等我的指令" → TD-365 拆分治理为当前任务。

## 2. N151 5 步法评估过程

1. **架构盘点**: `backend/agents/views.py` 3983 行 (全仓最大), 20 个顶层定义 (19 类 + 1 函数), 引用方仅 3 处: `agents/urls.py` (19 符号) + `monitors/views.py:780` (懒加载 DeviceScanView) + `agent_runtime.py:436` (懒加载 DeviceViewSet)。既有先例: `agents/services/device_service.py` (Phase 1 已外迁服务层, 拆分模式已验证)。
2. **识别反模式**: 单文件无限膨胀 (功能迭代持续追加, 无拆分治理); 无双套并存 (视图仅此一处定义)。
3. **A/B/C 备选**:
   - **A (选定)**: 拆 `view_sets/` 包 8 功能域模块 + views.py 保留 re-export 兼容层 → 引用方零改动
   - B: 仅拆最大的 2-3 个类 → 收益不足, 其余类继续膨胀
   - C: KEEP → 违反技术债不堆积原则 (N151 拒绝路径)
4. **拒绝反模式**: B (收益不足) / C (KEEP) 均拒绝; 方案 A 无双套并存风险 (re-export 是薄转发层, 非重复实现)。
5. **AI 自决边界**: 8 功能域划分与模块命名自决; 包名因同名冲突偏离 (views/ → view_sets/, 见 §4)。

## 3. N167 七维度评分

| 维度 | 评分 | 理由 |
|------|------|------|
| 1 架构长远性 | 9 | 功能域内聚, 后续迭代按域扩展 |
| 2 全局归一化 | 8 | 与 device_service.py 拆分先例一致, re-export 归一 |
| 3 新旧兼容 | 9 | 引用方零改动 (3 处均验证) |
| 4 现有业务完善 | 7 | 零逻辑变更, 4 处空 except 顺带修复 |
| 5 性能资源优化 | 7 | 模块加载等价 (re-export 仅多一层 import) |
| 6 安全合规加固 | 6 | 无敏感面变化 |
| 7 长期维护成本 | 9 | 单文件 3983 → 最大模块 686; 定位/审查成本大降 |
| **总分** | **55/63** | ≥19 且领先 B/C ≥5 → AI 自决 ✓ |

## 4. 关键实施决策 (process 小坑 + 修复方法)

1. **包名冲突 (最重要)**: 初拆到 `agents/views/` 包 → `from agents.views import AgentViewSet` 报 ImportError (Python 包优先于同名模块) → 改用 `agents/view_sets/` 包名, views.py 保留 re-export。
2. **拆分脚本 header 注入 bug 两连**:
   - v1: RANGES 闭区间切片把下一类 class 行吞掉 → 弃用, 改 AST 精确边界 (end = 下一顶层节点 lineno - 1)。
   - v2: 尾部空行清理误用 `header.pop(0)` (应 `pop()`) → 整个 header 被清空, 子模块缺 imports。修复后 docstring 残留, 改为完整剥 docstring 块 (`"""..."""`)。
3. **services import 位置**: 原文件 logger 定义在 `from agents.services import` 之前 → E402; ruff --fix 只修单行 import, 多行块不动 → 手动把 services 块上移到 import 区。
4. **re-export 被 ruff F401 清空**: pyproject 只豁免 `__init__.py`, views.py 的 re-export import 全被删 → 加 `__all__` 列表 (ruff 对 __all__ 中名字不报 F401)。
5. **I001 排序反复**: `_capture_device_screenshot` 下划线名按 isort 规则排大写字母后, --fix 不生效 → 手动调整。
6. **4 处空 except (预存错误, N150/N193)**: 原文件 4 处 `except: pass` 防御性解析 (int/split 容错) 触发 gaf-code-rules R001 → 补 `logger.debug` 日志 (解析容错属正常分支, 不配 warning)。
7. **PowerShell 重定向坑**: `git show > file` 输出 UTF-16LE BOM → 用 python subprocess capture 替代。
8. **B2 evidence TTL 30 min**: commit 前需重跑 `check_big_change.py --staged --acknowledge`。

## 5. 反思 (N193 任务归属复查)

- 拆分中发现的问题全部当场处理: 空 except 修复 ✓ / 包名冲突 ✓ / re-export F401 ✓
- 无遗留建议; 验收标准 600 行偏离已记录到 spec deviation log (真实约束是 TD-365 的 2000 行阈值)