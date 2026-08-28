# s36 Verification

## 命令与结果
| 验证 | 命令 | 结果 |
|------|------|------|
| 方法完整性 | 脚本断言 + AST 复核 | 59/59 (25+27+7) ✓ |
| 契约符号 | `import devices.adb.device` hasattr 19 符号 | NONE missing ✓ |
| ruff | `python -m ruff check agent/src/devices/adb/ --fix` | 51+24+25 F401 自动清理后 0 remaining ✓ |
| 专项测试 | 12 文件 (adb/ldopengl/retry/orchestrator/pipeline/engine_nodes...) | 459 passed, 2 skipped ✓ |
| 全量回归 | `pytest agent/tests/ -p no:django -o addopts=""` | **2305 passed, 3 skipped** (171s, 基线一致) ✓ |
| s35 修复回归 | L432 缩进修复后 ast.parse + 全量 | OK ✓ |

## 中间失败与根因
| 失败 | 根因 | 修复 |
|------|------|------|
| test_adb_device_extended ImportError: ADB_INPUT | D1 常量 re-export 被 F401 删 | __all__ 27 符号 |
| TypeError: object.__init__ | D2 MRO 到 object | mixin 继承 BaseDevice |
| test_ldopengl 3 处断言 | D3 源码物理位置断言 | 断言拼接两文件源码 |
| 4 文件收集 ERROR | D4 s35 遗留 L432 语法错误（R001 修复缩进） | 修复缩进 |
| 全量 import 契约漏扫 | D5 正则漏多行 import | AST 级扫描 |

## 结论
拆分行为等价：全量 2305 passed 与 s35 基线一致；引用方 src 零改动；唯一测试改动是源码位置断言的读取适配（test_ldopengl 3 处）。
