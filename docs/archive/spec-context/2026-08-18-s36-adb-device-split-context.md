# s36 — ADBDevice Split (2026-08-18) — spec-context 承载体

> B2 大修改承载体 (TD-342)。对应 spec: `docs/specs/archived/2026-08/2026-08-18-s36-adb-device-split.md`。

## N173 用时字段

- start_ts: 2026-08-18T19:58:00+08:00
- end_ts: 2026-08-18T20:58:00+08:00
- duration_min: 60
- within_baseline: true (大修改基线 60min, 边界达标)
- root_cause_if_over: 无

## 1. 用户决策原文

- 2026-08-18 循环模式（"继续" 强触发延续）：TD-365 大文件治理按 backend → agent → frontend → scripts 顺序接修，s36 = `worker/src/devices/adb/device.py`（1976 行，TD-365 剩余 6 个中的 agent 层第一个）。
- 方法论继承：s35（pipeline_engine.py 拆分）成功模式 + N202 lesson 8 项拆前检查清单。

## 2. N151 5 步法评估

1. **架构盘点**：device.py 单巨类 ADBDevice(BaseDevice) 1916 行 + 26 顶层常量；引用方 9 文件全 import ADBDevice 或实例化；测试 patch 点全实例级；方法 3 功能域（capture 25 / input 27 / lifecycle 7）内聚，类内交叉引用全在域内。
2. **识别反模式**：单文件 1976 行（TD-365 阈值 2000）——无双套并存、无硬编码。
3. **A/B/C 备选**：
   - A) 3 mixin 拆分（capture/input/lifecycle）+ 常量模块 —— 域内聚最高，s35 模式复用
   - B) 2 mixin（capture/input 合并 lifecycle 留主文件）—— 主文件仍 ~320 行
   - C) 保持现状登记延后 —— 违反循环模式接修指令
4. **拒绝反模式**：C 拒绝（任务明确）；B 拒绝（主文件仍大，且 lifecycle 与其他域无共享，独立 mixin 更均衡）。
5. **AI 自决**：选 A（总分 57/63，见 §3）。

## 3. N167 七维度评分

| 维度 | A 3-mixin | B 2-mixin | C 保持 |
|------|-----------|-----------|--------|
| 1 架构长远性 | 10 | 7 | 3 |
| 2 全局归一化 | 9 | 7 | 4 |
| 3 新旧兼容 | 9 | 9 | 10 |
| 4 现有业务完善 | 9 | 9 | 6 |
| 5 性能资源优化 | 8 | 8 | 5 |
| 6 安全合规加固 | 6 | 6 | 5 |
| 7 长期维护成本 | 6 | 6 | 5 |
| 合计 | **57** | 52 | 38 |

A ≥ 19 且领先 ≥ 5 → AI 自决 ✓

## 4. 关键实施决策

| # | 决策 | 背景 | 处理 |
|---|------|------|------|
| D1 | 常量 re-export 入 `__all__` | ruff --fix F401 自动删主文件未使用 re-export → test ImportError（s35 反模式重演） | `__all__` = ADBDevice + 26 常量 |
| D2 | mixin 继承 BaseDevice | lifecycle `super().__init__(device_id=...)` MRO 到 object → TypeError | 3 mixin + 主类全继承 BaseDevice，super() 链落到 BaseDevice |
| D3 | 测试源码断言适配 | test_ldopengl 3 处读 `device.__file__` 断言 method_map/fallback_order 物理位置 | 断言改读 device.py + adb_capture.py 拼接 |
| D4 | s35 遗留 L432 语法错误修复 | s35 R001 空 except 修复缩进错乱 + 修复后未重跑 pytest（验证缺口） | 本次修复 + 全量回归 2305 passed |
| D5 | AST import 契约扫描 | 正则 `[^\n]+` 漏多行括号 import（test_adb_device_extended 19 符号） | AST 级扫描替代正则 |

## 5. 验证 evidence

- 全量 `pytest agent/tests/ -p no:django -o addopts=""` = **2305 passed / 3 skipped**（171s，与 s35 基线一致）
- ruff 0 remaining；契约 19 符号 NONE missing；59/59 方法完整性
- evidence 三件套: `.ai-memory/evidence/active/2026-08-18-s36-adb-device-split/`

## 6. N193 反思（任务归属）

- 发现的 D4（s35 验证缺口——R001 修复后未重跑测试）当场纳入本次修复并全量回归。
- D5（import 契约扫描盲区）沉淀到 N202 lesson 更新（多行 import 检查项）。
- N202 更新项：⑨ 多行括号 import 契约（AST 级扫描）；⑩ 主文件 re-export 常量入 __all__ 防 F401；⑪ mixin super().__init__ 带参数 → 基类继承。