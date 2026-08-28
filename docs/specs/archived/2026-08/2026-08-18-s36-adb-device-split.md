# s36 — Split `agent/src/devices/adb/device.py` (1976 lines) into mixins (TD-365)

> **状态: ✅ 已归档** (2026-08-18) — 实现产物: `-` (拆分+验证), 归档副本: `docs/specs/archived/2026-08/2026-08-18-s36-adb-device-split.md`。沉淀: N202 lesson 更新 (D1/D2/D4/D5 新增检查项) + scripts/refactor 模板泛化 (常量块提取)。

> TD-365 大文件治理 batch 3。s34 views.py / s35 pipeline_engine.py 已闭环。
> 复用 s35 方法论 (N202 lesson 8 项拆前检查清单) + `scripts/refactor/split_large_python_file.py` 泛化引擎 (新增常量块提取能力)。

## 状态表

| Phase | 状态 | 完成时间 | commit | 验收 evidence |
|-------|------|---------|--------|--------------|
| P1 结构分析 + spec | ✅ | 2026-08-18 | | 59 方法 3 域分组 + AST 域 import 分析 |
| P2 拆分实现 | ✅ | 2026-08-18 | | 5 文件生成 + ruff 全过 + 契约 19 符号全通 |
| P3 验证 + commit | ⏳ | | | 全量 2305 passed / 3 skipped |
| P4 归档 + TD-365 更新 | ⏳ | | | |

## Deviation Log

| # | 偏离 | 根因 | 处理 |
|---|------|------|------|
| D1 | 常量 re-export 被 ruff F401 删 → test_adb_device_extended ImportError | 主文件 `from .adb_constants import X` 未入 `__all__` → --fix 自动删（s35 反模式重演） | `__all__` 含全部 26 常量名 |
| D2 | `super().__init__` TypeError: object.__init__ | mixin 继承 object，MRO 到 object 无参 __init__（s35 无此问题因 __init__ 无参） | 3 mixin + 主类全继承 BaseDevice |
| D3 | test_ldopengl 3 处源码断言失败 | 断言读 `device.py.__file__` 物理位置（method_map/fallback_order 已移 adb_capture.py） | 断言改读 device.py + adb_capture.py 拼接源码 |
| D4 | s35 遗留 pipeline_execution.py L432 语法错误（R001 修复缩进错乱） | s35 commit 前 R001 修复后未重跑 pytest（验证缺口） | 本次修复缩进 + 全量回归确认 |
| D5 | import 契约正则漏多行括号 import（test_adb_device_extended 19 符号） | `from X import (\n a,\n b)` 换行形式 `[^\n]+` 扫不到 | AST 级 import 契约扫描（s36_import_ast.py）|

## 背景

- `agent/src/devices/adb/device.py` 1976 行，单巨类 `ADBDevice(BaseDevice)` (L61-1976, 1916 行) + 顶层 28 常量 (L24-58)。
- 65 方法 3 大功能域：
  - **capture** (25 方法 ~930 行, L150-1083)：capture_screen + _capture_by_method + 14 个 _capture_* (screencap/scrcpy/droidcast/nemu/uiautomator2/ascreencap/nemu_ipc/ldopengl) + _find_nemu_window
  - **input** (27 方法 ~650 行, L1087-1737)：click/swipe/key_press/text_input + _*_by_method + _input_* (adb/maatouch/minitouch/u2/hermit/nemu_ipc) + _get_* 辅助 + _resolve_keycode
  - **lifecycle** (7 方法 ~260 行)：__init__/connect/disconnect/_cleanup_resources/get_resolution/get_device_info/reboot
- 类内交叉引用全部在域内（capture↔capture / input↔input），跨域仅 __init__ 读写实例属性 → 3 mixin 分组内聚。

## N202 8 项拆前检查结果

1. **patch 点**：`device._device = Mock(...)` (test_adb_device_extended ×10, test_retry) + `device.capture_screen` (test_orchestrator/s27/test_screenshot_stream_dedup) + `device.activate_window` (test_click_race_protection) + `device.emit_coord_trace` (test_monitor_coord_trace) — **全部实例属性/方法 patch，非模块属性 patch** → 拆分后语义不变，无需转发函数（与 s35 不同）。
2. **import 契约**：仅 `from devices.adb.device import ADBDevice`（`devices/adb/__init__.py` + `devices/center.py` + test_emulator_restart + test_retry）→ `__all__ = ["ADBDevice"]` + 常量 re-export 即可。
3. **decorator_list[0].lineno**：方法无装饰器（除 @require_operable 在 connect/click/swipe/key_press/text_input/get_resolution/get_device_info 上）→ 必须用 decorator_list[0].lineno 提取。
4. **header 过滤**：无删除需求（常量整体提出）。
5. **logger**：各 mixin 独立 `logger = logging.getLogger(__name__)`（无外部 patch `device.logger`）。
6. **全量测试验证**：agent 全量 pytest。
7. **re-export**：主文件 `from .adb_constants import <28 常量>`（防未来外部引用 device.py 顶层常量）+ `__all__`。
8. **常量契约**：28 个顶层常量 → 新模块 `adb_constants.py`，按域精确 EXTRA_IMPORTS（见 P2 表）。

## P1 结构分析结论

- 引用方 9 文件（src 4 + tests 5），全部 import ADBDevice 或实例化，无符号级依赖。
- 域 import 分布（header L3-20 → 各域）：
  - capture: contextlib/importlib/io/socket/struct/time/typing.Any/numpy/PIL.Image/core.retry.retry_screenshot/monitor.resources.record_screenshot/devices.base.require_operable + 常量 14 个
  - input: contextlib/json/socket/time/typing.Any/core.exceptions.DeviceError/core.retry.retry_input/devices.base.require_operable + 常量 6 个
  - lifecycle: contextlib/socket/typing.Any/core.exceptions.DeviceError/devices.base.{DeviceStatus,require_operable}/.pool.get_adb_pool + 常量 4 个
- 常量域归属：`*_METHOD` 14 个 → capture；`*_INPUT` 6 个 → input；`*_DEFAULT_PORT` 4 个 → lifecycle；`ASCREENCAP_REMOTE_PATH`/`ASCREENCAP_BMZ1_MAGIC`/`NEMU_IPC_DLL_TIMEOUT_SEC` → capture；`HERMIT_PACKAGE_NAME`/`LDOPENGL_DLL_TIMEOUT_SEC` → 无方法使用（保留在 adb_constants.py，主文件 re-export，不做删除决策）。

## P2 拆分实现

目标产物（`agent/src/devices/adb/`）：

| 文件 | 内容 | 预估行数 |
|------|------|---------|
| `adb_constants.py` | 28 个顶层常量 (L24-58, 含注释) | ~40 |
| `adb_capture.py` | ADBCaptureMixin — 25 方法 | ~950 |
| `adb_input.py` | ADBInputMixin — 27 方法 | ~670 |
| `adb_lifecycle.py` | ADBLifecycleMixin — 7 方法 | ~280 |
| `device.py` | ADBDevice(ADBLifecycleMixin, ADBCaptureMixin, ADBInputMixin) + header + 常量 re-export + `__all__=["ADBDevice"]` | ~100 |

- 方法体零改动复制（AST 边界提取），仅换文件归属。
- 每个 mixin 文件：域所需 header imports + `from .adb_constants import <域常量>` + `logger = logging.getLogger(__name__)` + class。
- 主文件保留：docstring + 完整 imports + logger + 常量 re-export + mixin imports + 类定义 + `__all__`。
- 脚本：`.trash/s36_split_device.py`（复制自 scripts/refactor 模板 + 常量块提取逻辑）。成功后把「常量块提取」合并回 `scripts/refactor/split_large_python_file.py` 泛化模板。

## P3 验证

1. `ruff check agent/src/devices/adb/`（先 --fix 再人工确认）
2. `python -m pytest agent/tests/ -p no:django -o addopts=""` 全量（基线 2305 passed）
3. 专项：test_adb_device_extended / test_emulator_restart / test_retry / test_ldopengl / test_orchestrator（ADBDevice 实例化 + patch 路径）
4. N193 任务归属：发现的预存问题当场纳入

## P4 归档

- spec → `docs/specs/archived/2026-08/2026-08-18-s36-adb-device-split.md` + hash 回填
- TD-365 更新 3/9 + active.md 状态行
- spec-context 承载体 + N173 用时回填 + evidence 三件套 + B2 + session

## 验收标准

- [x] device.py 11 行，类体仅继承 + docstring
- [x] 全量 agent 测试通过 2305 passed / 3 skipped（基线一致）
- [x] ruff 无新增问题（adb/ 全过；51+24 F401 自动清理均为未使用 import）
- [x] 引用方（__init__/center/测试）零改动（test_ldopengl 仅断言读取源调整，非引用契约）
- [x] 方法完整性：59/59（脚本断言 + AST 复核）
- [x] s35 遗留 L432 语法错误修复（D4）