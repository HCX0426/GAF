---
summary: GAF vs BD2-AUTO 对比与代码复用分析
applies_to: ['architecture', 'design']
key_decisions:
  - 一、概述
last_updated: 2026-08-17 (s30 确认仍有效)
---

# GAF vs BD2-AUTO 对比与代码复用分析

> 版本：2.0 | 日期：2026-05-23

## 一、概述

本文档全面对比 GAF（Game Automation Framework）与 BD2-AUTO 的差异，涵盖架构、技术栈、数据存储、UI、部署、功能差异和代码复用策略。GAF 是 BD2-AUTO 的下一代演进版本，采用 Agent-Server-Client 三层架构重构，保留了 BD2-AUTO 的核心能力，同时解决了其架构缺陷。

**核心结论**：BD2-AUTO 约 52% 的代码可**直接迁移**至 GAF，约 24% 需小幅修改，约 24% 需参考重写，仅 7 个模块需完全重写。GAF 相比 BD2-AUTO 新增 28 项功能（含13项超出原规划的自研能力），移除 7 项，改进 14 项（全部已完成）。

---

## 二、架构差异对比

| 维度 | BD2-AUTO | GAF |
|------|----------|-----|
| 架构模式 | 单进程单体 | Agent-Server-Client 三层架构 |
| 进程模型 | 单 Python 进程 | 多进程（Django + Celery + Agent） |
| 通信方式 | 直接方法调用 | HTTP REST + WebSocket |
| 部署方式 | 本地单机 | 本地单机 / Docker / 远程多机 |
| 扩展性 | 不可水平扩展 | Agent 可水平扩展 |
| 设备支持 | 单设备（Windows窗口+ADB模拟器） | 多设备多 Agent |

### BD2-AUTO 架构

```
┌──────────────────────────────────────────────────────────┐
│  BD2-AUTO (单进程)                                        │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Auto (上帝对象)                                   │   │
│  │  ├── Config (全局单例)                             │   │
│  │  ├── GamePackageManager (全局单例)                  │   │
│  │  ├── ChainManager                                 │   │
│  │  ├── MonitorManager (QObject)                     │   │
│  │  ├── OperationHandler                             │   │
│  │  ├── VerifyHandler                                │   │
│  │  ├── ScreenshotManager                            │   │
│  │  ├── InputController                              │   │
│  │  ├── ImageProcessor                               │   │
│  │  ├── OCRProcessor                                 │   │
│  │  └── WindowManager                                │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  PyQt6 GUI                                        │   │
│  │  ├── MainWindow                                   │   │
│  │  ├── TaskPanel                                    │   │
│  │  └── MonitorPanel                                 │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### GAF 架构

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Client (React)  │  │  Server (Django) │  │  Agent (Python)  │
│  - 仪表盘        │  │  - REST API      │  │  - TaskOrchestr. │
│  - 任务管理      │  │  - WebSocket     │  │  - ChainManager  │
│  - 设备监控      │  │  - Celery        │  │  - StateMachine  │
│  - 资源管理      │  │  - Django ORM    │  │  - MonitorMgr    │
│  - 系统设置      │  │  - Auth (JWT)    │  │  - Screenshot    │
│                  │  │                  │  │  - Input         │
│                  │  │                  │  │  - Image/OCR     │
│                  │  │                  │  │  - ADB Control   │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

---

## 三、技术栈差异

| 维度 | BD2-AUTO | GAF |
|------|----------|-----|
| **后端** | 无独立后端 | Django 5.2 + DRF + Channels |
| **前端** | PyQt6 | React 19 + TypeScript + Ant Design |
| **任务队列** | 无 | Celery + Redis |
| **实时通信** | PyQt6 Signal/Slot | WebSocket (Django Channels) |
| **数据库** | JSON 文件 | SQLite + WAL (Django ORM) |
| **缓存** | 无 | Redis |
| **认证** | 无 | JWT + Agent Token |
| **Agent 通信** | 直接调用 | WebSocket 长连接 |
| **截图** | Win32 API | Win32 API + WGC ctypes + ADB 降级链 |
| **ADB** | 基础ADB截图（screencap） | 完整降级链 (nemu→scrcpy→DroidCast→u2→screencap) |
| **OCR** | EasyOCR + PaddleOCR | **PaddleOCR + RapidOCR 双引擎** + 引擎注册表 + 竞速 + pHash缓存 |
| **图像识别** | OpenCV | OpenCV + **ONNX(YOLOv8) + AI分割(SAM/U²-Net)** |
| **LLM** | 无 | DeepSeek / OpenAI / 本地模型 |
| **任务引擎** | ChainManager | **三模式**：Pipeline(图执行) + ChainManager(链式) + StateMachine(状态机) |
| **状态管理** | 无 | Zustand |
| **构建工具** | 无 | Vite |

---

## 四、数据存储差异

| 维度 | BD2-AUTO | GAF |
|------|----------|-----|
| **存储方式** | JSON 文件 | SQLite + WAL |
| **配置存储** | `settings.json` | `AppSettings` 表 |
| **ROI 配置** | `rois.json` | `Task.params_config` JSON 字段 |
| **任务定义** | Python 代码 + `task_configs/*.json` | `Task.task_definition` JSON 字段 |
| **监控规则** | `monitor_config.json` | `MonitorRule.rule_definition` JSON 字段 |
| **资源包** | 文件目录 | `ResourcePack` 表 + 文件系统 |
| **执行记录** | 日志文件 | `TaskExecution` + `TaskStep` 表 |
| **用户数据** | 无 | `User` 表 |
| **LLM 用量** | 无 | `LLMUsageLog` 表 |
| **查询能力** | 文件遍历 | SQL 查询 + Django ORM |
| **并发安全** | 无 | 数据库事务 + 锁 |
| **数据迁移** | 无 | Django Migrations |

---

## 五、UI 差异

| 维度 | BD2-AUTO | GAF |
|------|----------|-----|
| **技术** | PyQt6 | React + Ant Design |
| **平台** | 仅 Windows 桌面 | Web 浏览器（跨平台） |
| **远程访问** | 不支持 | 支持（通过浏览器） |
| **多用户** | 不支持 | 支持多用户登录 |
| **实时截图** | PyQt6 QLabel | Canvas + WebSocket |
| **任务编辑** | 代码编辑 | 可视化编辑器 |
| **监控展示** | PyQt6 列表 | Web 仪表盘 |
| **响应式** | 固定窗口 | 响应式布局 |
| **主题** | 系统主题 | 亮色/暗色主题 |
| **国际化** | 中文 | 中文（可扩展） |

---

## 六、代码复用分析

### 6.1 复用策略统计

| 复用策略 | 模块数 | 占比 | 说明 |
|----------|--------|------|------|
| 直接迁移 | 22 | 52% | 无需修改或仅需格式调整 |
| 小幅修改 | 10 | 24% | 解耦全局依赖，改为依赖注入 |
| 参考重写 | 10 | 24% | 保留设计模式，重新实现 |
| 完全重写 | 7 | — | 架构不兼容，全新实现 |

### 6.2 GAF 三层架构映射

```
┌─────────────────────────────────────────────────────────────┐
│  Client 层                                                   │
│  - UI 展示 / 用户交互 / 配置管理 / 日志展示                    │
│  - WindowHelper (窗口选择)                                    │
│  - ConfigLoader (UI配置部分)                                  │
│  - Logger (日志展示桥接)                                      │
└──────────────────────┬──────────────────────────────────────┘
                       │ 事件/信号
┌──────────────────────▼──────────────────────────────────────┐
│  Agent 层                                                    │
│  - 任务编排 / 流程控制 / 策略决策                              │
│  - ChainManager + Step (任务编排引擎)                         │
│  - auto_task 装饰器 (任务生命周期)                             │
│  - MonitorManager (监控守护)                                  │
│  - AutoConfig (重试/超时策略)                                  │
│  - 任务定义脚本 (tasks/*.py)                                  │
└──────────────────────┬──────────────────────────────────────┘
                       │ 接口调用
┌──────────────────────▼──────────────────────────────────────┐
│  Server 层                                                   │
│  - 原子能力服务 / 设备控制 / 图像识别 / OCR                    │
│  - BaseDevice + DeviceManager + WindowsDevice (设备服务)      │
│  - ScreenshotManager + InputController (截图/输入服务)         │
│  - ImageProcessor + ColorProcessor (图像识别服务)              │
│  - OCRProcessor + EasyOCRWrapper + PaddleOCRWrapper (OCR服务) │
│  - CoordinateTransformer + RuntimeDisplayContext (坐标服务)   │
│  - OperationHandler + VerifyHandler (操作/验证服务)            │
│  - GamePackageManager + ConfigLoader (资源/配置服务)           │
│  - Logger + DebugImageSaver + ResourceManager (基础设施)      │
│  - type_aliases (共享类型)                                    │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 直接迁移模块清单

| 模块 | 说明 |
|------|------|
| AutoResult | 统一结果类 |
| 异常层次结构 | AutoBaseError 及子类 |
| DelayManager | 中断式延迟 |
| LockManager | 线程安全锁 |
| LogFormatter | 日志格式化 |
| BaseDevice | 设备抽象基类 |
| DeviceStatus | 设备状态枚举 |
| require_operable | 状态校验装饰器 |
| InputController | 鼠标/键盘操作 |
| ScreenshotManager | 截图策略 |
| WindowManager | 窗口管理 |
| WindowHelper | 窗口工具 |
| ColorProcessor | 颜色识别 |
| ColorSpace | 颜色空间枚举 |
| LRU 缓存 | 模板缓存 |
| 延迟加载 | 按需加载 |
| BaseOCR | OCR 抽象基类 |
| EasyOCRWrapper | EasyOCR 封装 |
| PaddleOCRWrapper | PaddleOCR 封装 |
| OCR 缓存 | MD5+3秒过期 |
| CoordinateTransformer | 坐标转换 |
| RuntimeDisplayContext | 显示上下文 |

### 6.4 完全重写模块清单

| 模块 | 原因 |
|------|------|
| MonitorManager | PyQt6 → EventBus |
| Auto 上帝对象 | 拆分为 TaskOrchestrator + AutomationServer |
| ConfigLoader | 全局单例 → Django ORM + ConfigProvider |
| Web UI | PyQt6 → React |
| Server 层 | 新增 Django 后端 |
| ADB 控制器 | 占位 → 完整实现 |
| 认证系统 | 无 → JWT |

---

## 七、各模块详细复用分析

### 7.1 任务执行模型 (auto_control/core/)

| 代码单元 | 复用策略 | 说明 |
|----------|---------|------|
| `AutoConfig` | 小幅修改 | 从全局单例解耦，改为可注入参数源 |
| `AutoResult` | 直接迁移 | 统一结果类，工厂方法可原样复用 |
| 异常层次结构 | 直接迁移 | AutoBaseError 及子类层次清晰 |
| `ChainManager` + `Step` | 参考重写 | 链式调用模式精巧，需重构为基于消息/指令的模式 |
| `with_retry_and_check` | 参考重写 | 装饰器逻辑可复用，设备获取需改为 Server 层接口 |
| `OperationHandler` | 参考重写 | 7种操作(pos_click/template_click/text_click/color_click/swipe/text_input/key_press)+@with_retry_and_check装饰器+窗口状态检查+颜色target解析(HSV/RGB/HEX/范围格式) |
| `VerifyHandler` | 参考重写 | 5种验证类型(exist/disappear/text/text_disappear/custom_verify)+窗口有效性感知+有效等待时间+验证失败现场保存 |
| `DelayManager` | 直接迁移 | stop_event.wait 中断式延迟设计优秀 |
| `LockManager` | 直接迁移 | 线程安全锁管理器，无外部依赖 |
| `LogFormatter` | 直接迁移 | 纯格式化工具，无副作用 |

### 7.2 设备控制层 (auto_control/devices/)

| 代码单元 | 复用策略 | 说明 |
|----------|---------|------|
| `BaseDevice(ABC)` | 直接迁移 | 抽象基类设计优秀，require_operable 装饰器通用 |
| `DeviceStatus` | 直接迁移 | 枚举定义，无依赖 |
| `require_operable` | 直接迁移 | 状态校验装饰器 |
| `DeviceManager` | 小幅修改 | 多设备管理可复用，需移除直接引用 |
| `WindowsDevice` | 小幅修改 | 组合模式良好，需与 Server 层配置解耦 |
| `InputController` | 直接迁移 | 鼠标/键盘操作封装完整 |
| `ScreenshotManager` | 直接迁移 | 多策略截图+SSIM策略检测+降级机制精巧 |
| `WindowManager` | 直接迁移 | 窗口查找/激活/置顶逻辑完整 |
| `WindowHelper` | 直接迁移 | 纯静态工具类 |
| `ADBDevice` | 参考重写 | 当前为占位实现，需完整实现 |

### 7.3 监控系统 (auto_control/monitor/)

| 代码单元 | 复用策略 | 说明 |
|----------|---------|------|
| `MonitorThread` 循环执行模式 | 参考重写 | 守护线程+stop_event 模式可复用，需与 PyQt6 解耦 |
| 动态加载任务模块机制 | 参考重写 | importlib 动态导入可复用，需适配插件注册 |
| `MonitorManager(QObject)` | 完全重写 | 强依赖 PyQt6，需改为事件总线 |

### 7.4 图像识别 (auto_control/image/)

| 代码单元 | 复用策略 | 说明 |
|----------|---------|------|
| `ImageProcessor.find_template()` | 小幅修改 | 核心逻辑可复用，CoordinateTransformer 需改为可注入 |
| LRU 缓存机制 | 直接迁移 | 模板缓存策略设计合理 |
| 延迟加载机制 | 直接迁移 | 按需加载模式可原样复用 |
| `ColorProcessor` | 直接迁移 | 多颜色空间识别，无外部耦合 |
| `ColorSpace` | 直接迁移 | 枚举定义 |

### 7.5 OCR (auto_control/ocr/)

| 代码单元 | 复用策略 | 说明 |
|----------|---------|------|
| `BaseOCR(ABC)` | 直接迁移 | 策略模式抽象基类 |
| `OCRProcessor` | 小幅修改 | 统一调用+缓存+坐标转换可复用，需改为可注入 |
| 缓存机制 | 直接迁移 | MD5+3秒过期+50条上限 |
| `EasyOCRWrapper` | 直接迁移 | GPU检测+批量识别+stop_event中断 |
| `PaddleOCRWrapper` | 直接迁移 | 新旧结果格式兼容 |
| `ocr_config.py` | 直接迁移 | 语言代码映射和引擎配置 |

### 7.6 工具类 (auto_control/utils/)

| 代码单元 | 复用策略 | 说明 |
|----------|---------|------|
| `CoordinateTransformer` | 直接迁移 | BASE→LOGICAL→PHYSICAL→SCREEN四级坐标转换 |
| `WindowManager` | 直接迁移 | 7个延迟常量精细控制窗口操作时序 |
| `RuntimeDisplayContext` | 直接迁移 | dataclass 设计简洁 |
| `type_aliases.py` | 直接迁移 | 类型别名和 Protocol 定义 |
| `DebugImageSaver` | 直接迁移 | 调试图标注和保存逻辑完整 |
| `ResourceManager` | 小幅修改 | 清理逻辑可复用，path_manager 需改为可注入 |

### 7.7 配置/调度 (core/)

| 代码单元 | 复用策略 | 说明 |
|----------|---------|------|
| `ConfigLoader` 加载逻辑 | 参考重写 | 多源+优先级合并模式可复用，全局单例需改为依赖注入 |
| `_load_config()` | 直接迁移 | 通用配置文件加载方法 |
| `_merge_configs()` | 直接迁移 | 配置合并逻辑 |
| `GamePackageManager` | 小幅修改 | 扫描/创建逻辑可复用，activate 需与 Server 层联动 |
| `Logger` | 小幅修改 | 日志多播+异步写入+轮转压缩设计优秀，需移除硬编码依赖 |
| `CompressedTimedRotatingFileHandler` | 直接迁移 | 日志轮转+压缩+清理 |
| `AsyncLogHandler` | 直接迁移 | 异步日志写入 |

### 7.8 任务定义和资源包 (auto_tasks/Default/)

| 代码单元 | 复用策略 | 说明 |
|----------|---------|------|
| 资源包目录结构 | 直接迁移 | tasks/templates/config/monitors 组织方式清晰 |
| `auto_task` 装饰器模式 | 参考重写 | 封装模式可复用，需与 Agent 层任务生命周期集成 |
| 链式调用风格 | 参考重写 | 风格可保留，底层需改为 Server 层接口调用 |
| ROI 配置管理 | 直接迁移 | 配置加载和查询逻辑 |
| monitors 弹窗处理模式 | 参考重写 | 模式可复用，需适配 Agent 层监控机制 |

---

## 八、新增功能清单

| 功能 | 说明 | GAF 模块 | 状态 |
|------|------|---------|------|
| Web UI | 浏览器访问的管理界面 | Frontend | ✅ |
| 多用户认证 | JWT 登录 + 角色权限 | accounts | ✅ |
| 多 Agent 管理 | 多设备同时执行任务 | agents | ✅ |
| REST API | 标准化 HTTP 接口 | DRF ViewSets | ✅ |
| WebSocket 通信 | 实时双向通信 | Django Channels | ✅ |
| Pipeline 图执行引擎 | 16节点类型+条件分支+校验器 | engine/ | ✅ 超出规划 |
| 自定义 JSON 任务 | 无需编码创建任务 | engine/parser.py | ✅ MaaFramework协议兼容 |
| 可视化任务编辑器 | 拖拽式编辑 | Frontend TaskEditor | ❌ 待实现 |
| 定时任务 | Cron 表达式调度 | Celery Beat | ✅ |
| LLM 集成 | 智能分析和问答 | Skills / QA | ✅ |
| ADB 完整支持 | 模拟器控制降级链(6级截图+4级输入) | ADBController | ✅ |
| 资源包管理 | 导入/导出/版本控制 | ResourcePack | ✅ |
| 监控规则热更新 | 运行时更新规则 | MonitorManager | ✅ |
| WGC 截图 (Win10+) | ctypes D3D11+WinRT 高性能截图 | wgc.py | ✅ 超出规划 |
| 截图竞速选择 | 基准测试+自动选最优 | benchmark.py | ✅ 超出规划 |
| 5层异常恢复 | 策略模式分级恢复 | recovery.py | ✅ 超出规划 |
| 高级输入 (FPS) | MessageInputFPS/MouseLockFollow/BlockInput | advanced_input.py | ✅ 超出规划 |
| ONNX 推理 | YOLOv8 目标检测 (DirectML/CUDA) | onnx_engine.py | ✅ 超出规划 |
| AI 分割 | SAM/U²-Net 智能抠图 | segmentation.py | ✅ 超出规划 |
| 录制回放 | 步骤录制→Pipeline自动转换 | recording/ | ✅ 超出规划 |
| 脚本 DSL | 自定义脚本语言 | script_dsl.py | ✅ 超出规划 |
| 模拟器同步 | 主控-镜像多实例同步 | emulator_sync.py | ✅ 超出规划 |
| 设备插件系统 | CapturePlugin/InputPlugin 可插拔 | plugin.py | ✅ 超出规划 |
| OCR 引擎注册表 | 多引擎注册+竞速基准测试 | registry.py | ✅ 超出规划 |
| 数据库持久化 | SQLite + WAL | Django ORM | ✅ |
| 数据备份 | 自动备份策略 | BackupService | ✅ |
| Docker 部署 | 容器化部署 | Docker Compose | ❌ 待实现 |
| 技术问答 | LLM 驱动的问答系统 | QA Module | ✅ |
| 截图缓存 | TTL 缓存 + SSIM 检测 | FramePool + ScreenshotCache | ✅ |

---

## 九、移除功能清单

| 功能 | BD2-AUTO | 移除原因 |
|------|----------|---------|
| PyQt6 GUI | 桌面界面 | 改用 React Web UI |
| Auto 上帝对象 | 核心入口 | 拆分为 TaskOrchestrator + AutomationServer |
| 全局 config 单例 | 配置管理 | 改为 Django ORM + ConfigProvider |
| 全局 game_package_manager | 资源管理 | 改为 Django ORM + ResourceService |
| pyqtSignal | 信号机制 | 改为 EventBus |
| QObject 继承 | MonitorManager | 改为纯 Python + EventBus |
| Python 代码任务定义 | 唯一任务格式 | 改为 JSON/YAML 可序列化定义 |
| 直接方法调用 | 模块间通信 | 改为事件驱动 + 依赖注入 |

---

## 十、改进功能清单

| 功能 | BD2-AUTO | GAF 改进 | 状态 |
|------|----------|---------|------|
| **截图** | 单一策略 | 降级链(WGC→GDI→PrintWindow)+SSIM+FramePool | ✅ |
| **ADB 控制** | 占位实现 | 完整降级链 (6级截图+4级输入) | ✅ |
| **任务执行** | 链式调用 | **Pipeline(图执行)+ChainManager(链式)+StateMachine(状态机)** 三模式 | ✅ |
| **监控** | PyQt6 线程 | 独立线程 + 事件总线 + 热更新 | ✅ |
| **配置管理** | JSON 文件 | Django ORM + Web UI | ✅ |
| **日志系统** | 文件日志 | 文件日志 + WebSocket 实时推送 | ✅ |
| **错误处理** | 简单重试 | 5层恢复策略 + 卡顿检测 + 心跳超时 | ✅ |
| **坐标转换** | 全局单例 | 依赖注入 + 分辨率适配 | ✅ |
| **模板缓存** | 简单 LRU | LRU + 资源切换自动清理 | ✅ |
| **设备管理** | 单设备 | 多设备 + 设备插件 + 并发控制 | ✅ |
| **资源包** | 文件目录 | 数据库 + 版本控制 + 导入导出 | ✅ |
| **任务定义** | Python 代码 | Pipeline JSON + MaaFramework协议兼容 + 可视化编辑(待实现) | ✅ |
| **权限控制** | 无 | JWT + 角色权限 | ✅ |
| **部署** | 手动 | 一键启动 + Docker(待实现) + 远程 | ✅ |

---

## 十一、迁移路径

### 11.1 数据迁移

```
BD2-AUTO                          GAF
─────────                         ─────
settings.json          ──►        AppSettings 表
rois.json              ──►        Task.params_config
task_configs/*.json    ──►        Task.task_definition
monitor_config.json    ──►        MonitorRule.rule_definition
资源包目录/             ──►        ResourcePack + 文件系统
日志文件/               ──►        TaskExecution + TaskStep
```

### 11.2 迁移脚本

GAF 提供 `scripts/migrate_bd2auto.py` 脚本，自动完成数据迁移：

```bash
python manage.py migrate_bd2auto --source /path/to/bd2-auto/
```

### 11.3 兼容性

| 兼容项 | 说明 |
|--------|------|
| 资源包目录结构 | 完全兼容，可直接导入 |
| 模板图片 | 完全兼容 |
| ROI 配置 | 格式转换后兼容 |
| 任务定义 | Python 代码需手动迁移为 JSON |
| 监控规则 | 格式转换后兼容 |

---

## 十二、关键重构要点

1. **拆解 Auto 上帝对象**：当前 `Auto` 类承担初始化、代理、资源切换等多重职责，需拆分为 Agent 层 `TaskOrchestrator` 和 Server 层 `AutomationServer`
2. **消除循环引用**：OperationHandler/VerifyHandler/DeviceHandler/ChainManager 均持有 `self.auto`，需改为依赖注入
3. **全局单例解耦**：`config` 和 `game_package_manager` 需改为依赖注入
4. **ChainManager 指令化**：步骤定义需支持可序列化，便于 Agent-Server 消息传递
5. **事件驱动替代直接调用**：设备状态变更、分辨率同步等改为事件驱动
6. **PyQt6 解耦**：MonitorManager 的 QObject/pyqtSignal 需改为事件总线

---

## 十三、跨平台兼容性分析

BD2-AUTO 是 **Windows-only** 项目，依赖 PyQt6 GUI + Win32 API，但其模块化程度较高，大量模块为纯 Python 实现，具备良好的跨平台迁移基础。

### 13.1 可直接迁移的跨平台模块

BD2-AUTO 的22个核心模块大多为纯 Python 实现，天然跨平台：

| 模块 | 说明 | 跨平台原因 |
|------|------|-----------|
| AutoResult | 统一返回值封装 | 纯 Python 数据类 |
| 异常层次 | 分层异常体系 | 纯 Python 类继承 |
| DelayManager | 延迟管理器 | 纯 Python 定时逻辑 |
| LockManager | 锁管理器 | 纯 Python 线程同步 |
| LogFormatter | 日志格式化 | 纯 Python 字符串处理 |
| BaseDevice | 设备基类 | 抽象接口，无平台依赖 |
| DeviceStatus | 设备状态枚举 | 纯 Python 枚举 |
| InputController | 输入控制器 | 基类抽象，平台实现在子类 |
| ScreenshotManager | 截图管理器 | 基类抽象，平台实现在子类 |
| WindowManager | 窗口管理器 | 基类抽象，平台实现在子类 |
| ColorProcessor | 颜色处理器 | 纯 NumPy 运算 |
| ColorSpace | 颜色空间转换 | 纯数学运算 |
| LRU缓存 | 最近最少使用缓存 | 纯 Python 数据结构 |
| 延迟加载 | Lazy 加载工具 | 纯 Python 描述符 |
| BaseOCR | OCR 基类 | 抽象接口 |
| EasyOCRWrapper | EasyOCR 封装 | EasyOCR 跨平台 |
| PaddleOCRWrapper | PaddleOCR 封装 | PaddleOCR 跨平台 |
| OCR缓存 | OCR 结果缓存 | 纯 Python 缓存逻辑 |
| CoordinateTransformer | 坐标变换器 | 纯数学运算 |
| RuntimeDisplayContext | 运行时显示上下文 | 纯 Python 上下文管理 |
| type_aliases | 类型别名 | 纯类型定义 |
| DebugImageSaver | 调试图片保存 | 纯 Python 文件操作 |

### 13.2 需要平台适配的模块

| 模块 | Windows 依赖 | 适配方案 |
|------|-------------|---------|
| WindowsDevice | Win32 API（FindWindow/EnumWindows/GetWindowRect 等） | 拆分为 BaseDevice + 平台子类 |
| ADBDevice | ADB 命令 | ✅ 已跨平台，无需适配 |
| WindowManager | Win32 `FindWindow` / `EnumWindows` | macOS: `NSWorkspace` / Linux: X11 `XQueryTree` |
| InputController | `SendInput` / `PostMessage` | macOS: `CGEventPost` / Linux: `XTest` + `uinput` |

### 13.3 UI 跨平台方案

| 原方案 | 问题 | GAF 方案 |
|--------|------|---------|
| PyQt6 GUI | PyQt6 虽跨平台，但 BD2-AUTO 的 MonitorManager 深度绑定 `QObject`/`pyqtSignal` | ✅ GAF 已采用 React Web UI，天然跨平台 |
| 本地桌面窗口 | 仅 Windows 桌面可见 | ✅ 浏览器访问，任意平台可用 |

GAF 的 React Web UI 方案已从根本上解决了 UI 跨平台问题。

### 13.4 GAF 架构的跨平台优势

GAF 的 **Agent-Server-Client** 三层架构天然支持跨平台：

| 层 | 组件 | 跨平台 | 说明 |
|----|------|--------|------|
| Client | React Web UI | ✅ | 浏览器访问，任意平台 |
| Server | Django 后端 | ✅ | Python 跨平台运行 |
| Agent | 自动化代理 | ⚠️ 需适配 | 截图/输入/窗口管理依赖平台 API |

仅 Agent 层需要平台适配，Server 和 Client 层完全跨平台。

### 13.5 对 GAF 的启示

| # | 启示 | 说明 |
|---|------|------|
| 1 | BaseDevice + 平台子类 | 将 BD2-AUTO 的 `WindowsDevice` 拆分为平台无关的 `BaseDevice` + 平台特定的 `WindowsDevice` / `MacOSDevice` / `LinuxDevice`，GAF 已有 `BaseDevice` 抽象，需确保接口不绑定 Windows 概念 |
| 2 | 22个纯 Python 模块直接复用 | AutoResult、异常层次、DelayManager、LockManager、ColorProcessor、LRU缓存等模块可直接参考或迁移，无需平台适配 |
| 3 | ADBDevice 作为跨平台基准 | ADBDevice 基于 ADB 命令，完全跨平台，应作为 GAF 的基准设备实现 |
| 4 | Agent 层平台插件化 | Agent 的截图/输入/窗口管理应设计为可插拔的平台插件，运行时根据 `sys.platform` 自动加载对应实现 |