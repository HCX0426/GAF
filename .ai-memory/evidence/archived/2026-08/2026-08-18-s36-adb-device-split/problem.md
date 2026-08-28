# s36 Problem — Split ADBDevice (1976 lines)

## 任务
TD-365 batch 3：`agent/src/devices/adb/device.py` 1976 行单巨类拆分为 mixin 架构。

## 前置扫描（N202 8 项清单）
- patch 点：全部实例级（`device._device` / `device.capture_screen` / `device.activate_window` / `device.emit_coord_trace`）→ 无模块属性 patch → 无需转发函数
- import 契约：`from devices.adb.device import ADBDevice`（__init__/center）+ test_adb_device_extended 19 符号（含 18 常量）+ test_ldopengl LDOPENGL_METHOD（**多行括号 import，正则漏扫 → AST 级扫描修正**）
- 方法 59 个 3 域：capture 25 / input 27 / lifecycle 7
- 域 import 分布 AST 分析（capture: numpy/PIL/retry_screenshot/record_screenshot; input: DeviceError/retry_input; lifecycle: BaseDevice/DeviceStatus/get_adb_pool）

## 目标结构
- `adb_constants.py`：26 顶层常量（L24-58）
- `adb_capture.py`：ADBCaptureMixin (25 方法, 973 行)
- `adb_input.py`：ADBInputMixin (27 方法, 720 行)
- `adb_lifecycle.py`：ADBLifecycleMixin (7 方法, 260 行)
- `device.py`：ADBDevice(ADBLifecycleMixin, ADBCaptureMixin, ADBInputMixin, BaseDevice) 11 行 + __all__ 27 符号

## 方法
复用 `scripts/refactor/split_large_python_file.py` 泛化引擎（s35），扩展常量块提取 + BaseDevice mixin 继承。脚本 `.trash/s36_split_device.py`，断言 59/59 完整性。
