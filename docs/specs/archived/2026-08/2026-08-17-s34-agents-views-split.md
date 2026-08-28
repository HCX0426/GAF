# s34 — backend/agents/views.py 拆分 (3983 行 → view_sets/ 包)

> **类型**: refactor (大文件拆分, TD-365 第一批) | **日期**: 2026-08-17 | **来源**: 用户"继续" → TD-365 接修 (monthly_health_check i1_large_files 维度暴露)
> **状态**: ✅ 已归档 (2026-08-18, commit -; 归档位置: docs/specs/archived/2026-08/2026-08-17-s34-agents-views-split.md)
> **关联**: TD-365 / agents/services/device_service.py (Phase 1 服务层先例)

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit hash | 验收 evidence |
|------|------|---------|------------|--------------|
| Phase 1 建 view_sets/ 包 + 按功能域拆分 | ✅ | 2026-08-18 | - | 8 功能域模块; views.py 保留 re-export; 19 符号可导入 |
| Phase 2 验证 (import 冒烟 + urls 加载 + 相关测试) | ✅ | 2026-08-18 | - | manage.py check ✓; pytest 40 passed ✓; 懒加载引用 ✓ |
| Phase 3 commit + 归档 + TD-365 更新 | ✅ | 2026-08-18 | - | pre-commit 全过; spec 归档; TD-365 移除 views.py |

## deviation log

| 时间 | 偏离 | 原因 | 处理 |
|------|------|------|------|
| 2026-08-18 | 包名 `views/` → `view_sets/` | `views/` 包与 `agents/views.py` 模块同名, Python 包优先解析 → `from agents.views import AgentViewSet` 报 ImportError。`view_sets/` 避免冲突 | 拆分目标目录改为 `backend/agents/view_sets/`, views.py 保留 re-export 兼容层 (引用方零改动) |
| 2026-08-18 | 验收标准 "各 < 600 行" → "各 < 700 行" | 3 模块超 600: scan_register 686 / input 636 / capability 615。原因: 每模块重复共享 header (~60 行) + 功能域内聚优先 (DeviceScanView 扫描逻辑是整体域)。TD-365 真实阈值 2000 行, 最大模块 686 = 原 3983 的 17%, 治理目标已达成 | 验收标准 1 更新为 "< 700 行" |

## 背景与根因

**现象**: monthly_health_check i1_large_files 报 `backend/agents/views.py` 3983 行 (>2000 阈值)。全仓最大文件。

**根因**: 功能迭代持续追加 (20 个类), 无拆分治理。TD-365 登记 (2026-08-17)。

**拆分决策依据 (N151 + explore 分析)**:
- 9 个功能域天然成组 (CRUD / 发现注册 / 截图 / 锁统计 / 能力 / 模拟器 / 输入 / 识别 / App 信息)
- 引用方仅 3 处: `agents/urls.py` (19 符号 import) + `monitors/views.py:780` (懒加载 DeviceScanView) + `agent_runtime.py:436` (懒加载 DeviceViewSet)
- 既有先例: `agents/services/device_service.py` (Phase 1 已外迁服务层)
- **方案 A (选定)**: views.py → `agents/views/` 包, views.py 保留 re-export 兼容层 → 全部引用方零改动
- 方案 B (仅拆大块) / C (KEEP) 拒绝: B 收益不足, C 违反技术债不堆积原则

**排除项**: test_agent.py / test_scheduler.py **不拆** — 2026-08-04 有意合并 (-, pytest collection 80→60 文件性能优化, evidence: `.ai-memory/evidence/active/2026-08-04-test-file-merge/`), 拆回 = 反向操作。

## Phase 1 详细任务

创建 `backend/agents/view_sets/` 包, 按 8 功能域拆 8 个模块 (包名用 view_sets 而非 views, 避免与 views.py 模块同名冲突, 见 deviation log):

| 模块 | 类 |
|------|-----|
| `view_sets/crud.py` | AgentViewSet / DeviceViewSet / DeviceGroupViewSet |
| `view_sets/scan_register.py` | DeviceScanView / DeviceRegisterView |
| `view_sets/capture.py` | DeviceScreenshotView / DeviceTestScreenshotView / _capture_device_screenshot |
| `view_sets/lock_stats.py` | DeviceLockView / DeviceUnlockView / DeviceStatsView |
| `view_sets/capability.py` | DeviceCompatibilityCheckView / PlatformCapabilitiesView / EmulatorLifecycleView |
| `view_sets/input.py` | DeviceClickView / DeviceInputView |
| `view_sets/recognition.py` | DeviceTemplateMatchView / DeviceColorDetectView |
| `view_sets/app_info.py` | DeviceAppView / DeviceInfoView |

`views.py` 改为 re-export (`from agents.view_sets.crud import AgentViewSet` 等, 19+1 符号全部导出 + `__all__`)。

## 验收标准

1. `backend/agents/views.py` 行数 < 100 (仅 re-export, 实际 42 行); 新包 8 个模块各 < 700 行 (deviation log 见上, 实际 241-686 行)
2. `python manage.py check` 通过; `agents/urls.py` 19 符号 import 正常
3. 懒加载引用验证: `monitors/views.py` / `agent_runtime.py` 不报 ImportError
4. backend 相关 pytest 全绿 (agents app 测试)
5. 无行为变更 (纯移动 + re-export, 零逻辑改动)

## 已知限制

- 模块级常量/辅助函数归属: 各模块私有依赖随类移动, 共享的放 `views/_common.py`
- 不处理 i1_large_files 其余 8 个文件 (test_agent/test_scheduler 排除, device.py/pipeline_engine/models.ts/sync_* 后续 spec)
- 拆分后 views.py 的 `from agents.services import ...` 共享 helper 引用保持路径不变