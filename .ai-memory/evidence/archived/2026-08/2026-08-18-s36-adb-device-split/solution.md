# s36 Solution — 拆分产物与关键决策

## 5 文件产物
| 文件 | 内容 | 行数 |
|------|------|------|
| adb_constants.py | 26 顶层常量 + docstring | ~40 |
| adb_capture.py | ADBCaptureMixin(BaseDevice) — 25 方法 | 973 |
| adb_input.py | ADBInputMixin(BaseDevice) — 27 方法 | 720 |
| adb_lifecycle.py | ADBLifecycleMixin(BaseDevice) — 7 方法 | 260 |
| device.py | ADBDevice(ADBLifecycleMixin, ADBCaptureMixin, ADBInputMixin, BaseDevice) + __all__ = [ADBDevice + 26 常量] | 11 |

## 关键决策
1. **D1 常量 re-export F401 保护**：主文件 `from .adb_constants import <26>` 必须进 `__all__`（否则 ruff --fix 自动删 → test_adb_device_extended ImportError）。s35 反模式重演。
2. **D2 mixin 继承 BaseDevice**：lifecycle `super().__init__`（带参数）在 MRO 到 object 时 TypeError。3 mixin + 主类全继承 BaseDevice，super() 链正确落到 BaseDevice。
3. **D3 测试源码断言适配**：test_ldopengl 3 处断言读 `device.__file__` 物理源码（method_map/fallback_order 位置）→ 改读 device.py + adb_capture.py 拼接。
4. **D4 s35 遗留 L432 语法错误修复**：R001 空 except 修复时缩进错乱（except 顶格）→ 修复（except 对齐 try）+ 全量回归。
5. **D5 AST import 契约扫描**：正则 `from X import ([^\n]+)` 漏多行括号 import（test_adb_device_extended 19 符号）。改 AST 扫描。

## 配置要点（脚本复用时）
- BASE_IMPORTS 按域：capture 13 个 header import + 14 常量 / input 8 个 + 6 常量 / lifecycle 7 个 + 4 常量
- logger 各域独立 `logging.getLogger(__name__)`
- 常量域归属：*_METHOD → capture; *_INPUT → input; *_DEFAULT_PORT → lifecycle; 无使用常量（HERMIT_PACKAGE_NAME/LDOPENGL_DLL_TIMEOUT_SEC）保留在常量模块不删
