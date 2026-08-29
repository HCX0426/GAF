---
spec: 2026-08-29-naming-c-device-emulator
title: 命名归一化 C-1：Device.emulator 字段 → emulator_brand
status: active
created: 2026-08-29
estimated_effort: 0.5 day
risk: high
depends_on: []
source: docs/analysis/concept-naming-normalization.md §1/§5(4)/§7
---

# 命名归一化 C-1：Device.emulator 字段 → emulator_brand

## 1. 背景与动机 (Background)

`backend/agents/models.py:323` 的 `Device.emulator` 字段是**自由文本模拟器品牌**（如 "LDPlayer"/"BlueStacks"），却与 `device_type='emulator'` 这个**设备类型枚举值**同名，造成语义混淆（评估稿 §5 决策 4、§7）。全仓 grep `Device.emulator` 共 40 命中，外加 `device_type='emulator'` 值 26 命中，易在重构时误伤。

本 spec 将字段重命名为 `emulator_brand`，与 `device_type` 枚举值彻底解耦，属高危（触及 API 契约 + DB 迁移 + 前端生成类型）。

## 2. 核心问题 (Problem)

| 项 | 现状 | 目标 |
|----|------|------|
| `Device.emulator` 字段 | 品牌自由文本，名与 `device_type='emulator'` 冲突 | `Device.emulator_brand` |
| `device_type='emulator'` | 枚举值（**保持不变**） | 不变 |

## 3. 目标 (Goals)

1. 字段重命名 `emulator` → `emulator_brand`，语义清晰。
2. 生成可逆 Django 迁移（数据零丢失）。
3. 前端 `api.generated.ts` + `models/device.ts` 重生成并替换引用。
4. 全仓 import/属性访问改写，不影响 `device_type` 枚举值。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 后端模型 + 迁移 + serializers/views | ⏳ |
| P2 | 前端类型重生成 + 引用替换 | ⏳ |
| P3 | 测试 + 验收 | ⏳ |

#### Task P1.1: 后端模型与迁移

- `backend/agents/models.py:323`：`emulator = models.CharField(...)` → `emulator_brand = models.CharField(...)`。
- 生成迁移 `RenameField` model `Device` `emulator`→`emulator_brand`（Django 自动保留数据）。
- `backend/agents/serializers.py`：`DeviceSerializer` 字段 `emulator`→`emulator_brand`（含读/写）。
- `backend/agents/views.py` / `device_service.py`：属性访问 `.emulator`→`.emulator_brand`（grep 40 命中逐项确认，排除 `device_type='emulator'`）。

#### Task P1.2: 前端类型重生成

- 重新运行前端 OpenAPI 类型生成（`api.generated.ts` / `models/device.ts`），替换 `emulator`→`emulator_brand`。
- `frontend/src` 组件属性访问 `.emulator`→`.emulator_brand`（grep 确认）。

#### Task P1.3: 文档同步

- 评估稿 §7 命中计数更新；`docs/analysis/concept-naming-normalization.md` 标记 C-1 完成。

## 5. 测试与验收 (Testing)

- **后端单测**：`agents/tests/` 创建设备（`device_type='emulator'`, `emulator_brand='LDPlayer'`），断言序列化往返正确。
- **迁移验证**：`conda run -n gaf python manage.py makemigrations --check` 无 diff；迁移 up/down 可逆。
- **前端类型检查**：`tsc --noEmit` 通过，无 `emulator` 残留（除 `device_type` 字面量）。
- **全量回归**：`pytest backend -k device` + 前端 lint。

## 6. 回滚 (Rollback)

- 迁移 `RenameField` 反向即恢复原字段名；代码 revert 本 spec commit。
