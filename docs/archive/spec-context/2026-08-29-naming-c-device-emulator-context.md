---
spec: 2026-08-29-naming-c-device-emulator
title: 命名归一化 C-1：Device.emulator → emulator_brand（执行上下文）
type: B2 大修改载体 (N151/N167/N173)
date: 2026-08-29
start_ts: 2026-08-29T22:05:00+08:00
end_ts: 2026-08-29T22:35:00+08:00
duration_min: 30
within_baseline: true
root_cause_if_over: n/a
---

# Spec Context — C-1 Device.emulator → emulator_brand

## N151 架构盘点（5 步）

1. **架构盘点**：`Device.emulator`(models.py:323) 为自由文本模拟器品牌字段，与 `device_type='emulator'` 枚举值同名造成语义混淆；跨 `agents` + `tasks` 两 app 共 16 处属性/线协议引用 + 1 处迁移 + 前端类型。
2. **识别反模式**：字段名与枚举值撞名 → 重构期易误伤；线协议键 `emulator` 与 `device_bridge.discovery.emulator` 模块 / `EmulatorInfo.emulator` 同形但语义不同（已显式排除）。
3. **A/B/C 备选**：A=仅文档标注不改名（拒绝：治标不治本）；B=字段重命名 `emulator_brand`（采用）；C=改为 `emulator_type`（拒绝：与 `device_type` 仍混淆）。
4. **七维评分**：见下；总分领先且 ≥19，自决推进。
5. **拒绝双套 / 最小化**：单一 `emulator_brand`；`device_type='emulator'` 枚举值、`device_bridge.discovery.emulator` 模块、`EmulatorInfo.emulator` 一律保留不改。

## N167 七维评估（大修改）

| 维度 | 评分 | 说明 |
|------|------|------|
| 1 架构长远性 | 5 | 字段名与设备类型枚举彻底解耦，语义零歧义 |
| 2 全局归一化 | 5 | 后端+前端+线协议键+迁移全栈统一为 `emulator_brand` |
| 3 扩展性 | 4 | 品牌字段可独立扩展，不依赖 `device_type` |
| 4 兼容性 | 4 | `RenameField` 迁移保数据；线协议键同步改名 |
| 5 可观测性 | 4 | 日志/序列化字段名一致，便于排查 |
| 6 测试覆盖 | 4 | 序列化往返 + makemigrations --check + 前端类型静态校验 |
| 7 长期维护成本 | 5 | 消除「emulator 指字段还是枚举」的认知负担 |
| **总分** | **31** | 领先且 ≥19，自决推进 |

## N173 用时测量

- start_ts: 2026-08-29T22:05:00+08:00
- end_ts: 2026-08-29T22:35:00+08:00
- duration_min: 30
- within_baseline: true（estimated 0.5 day；实际含迁移+前端类型编辑，<60min 基线）
- root_cause_if_over: n/a
