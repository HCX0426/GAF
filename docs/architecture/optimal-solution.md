---
summary: GAF 最优方案选择 — 四方对比与实施路线
applies_to: ['architecture', 'design']
applies_to_code_paths:
  - backend/
  - agent/
key_decisions:
  - 四、混合择优策略
  - 五、关键设计决策
last_updated: 2026-07-12
---

# GAF 最优方案选择 — 四方对比与实施路线

> 版本：5.4 | 日期：2026-05-27 | **v5.4: Phase 16 AI 独立菜单架构 + Phase 17 AbortController 修复 + 文档全面同步**
> 基于：MaaFramework / Alas / ok-script / BD2-AUTO 四方深度源码分析（v3.0 已源码验证）
> GAF 定位：**PC 窗口（Windows / macOS / Linux）+ 模拟器（ADB）**，不需要手机端
> 跨平台策略：**Windows 优先实现，macOS/Linux 架构预留 + 核心模块逐步适配**

## 一、分析对象

| 项目 | 定位 | 语言 | 核心优势 | 分析文档 |
|------|------|------|---------|---------|
| **MaaFramework** | 通用游戏自动化 SDK | C++ | Windows 控制（6截图+3输入9变体）+ Pipeline JSON 最完整 + 10种识别 | GAF-vs-MaaFramework-analysis.md |
| **Alas** | 碧蓝航线 7×24 专用 | Python | 模拟器 ADB 最全（10截图+6输入）+ 模拟器管理(8类) + 异常恢复 + YAML→GUI | GAF-vs-Alas-analysis.md |
| **ok-script** | 原神/崩坏专精 | Python | WGC 纯 ctypes 实现 + BitBlt 缓存 + 子窗口合成 + Debug 浮层 + 拟人化 | GAF-vs-ok-script-analysis.md |
| **BD2-AUTO** | 通用游戏自动化（GAF 前身） | Python | ChainManager 链式执行 + VerifyHandler(5种验证) + 门面模式解耦 | GAF-vs-BD2-AUTO-analysis.md |

---

## 二、GAF 设备定位

**GAF 控制两类设备：PC 窗口（跨三平台）+ 模拟器（通过 ADB）。不需要手机端。**

| 设备类型 | 控制方式 | 截图方式 | 输入方式 |
|---------|---------|---------|---------|
| **Windows 窗口** | Win32 API | WGC / BitBlt / PrintWindow / DXGI / GDI | SendInput / PostMessage / SendMessage |
| **macOS 窗口** | CoreGraphics / CGEvent | CGWindowListCreateImage / screencapture / IOSurface | CGEventPost / CGEventCreateMouseEvent / AppleScript |
| **Linux 窗口** | X11 / Wayland / uinput | XGetImage / XShmGetImage / xdg-desktop-portal / pipewire | XTestFakeKeyEvent / XSendEvent / uinput / evdev |
| **模拟器（跨平台）** | ADB | scrcpy / DroidCast / NemuIpc / LDOpenGL / ADB screencap | MaaTouch / minitouch / ADB input |

**跨平台兼容性说明：**

- **Windows**：功能最完整，所有截图/输入方式均可用，优先实现
- **macOS**：CoreGraphics 截图 + CGEvent 输入可覆盖大部分场景，模拟器通过 ADB 统一控制
- **Linux**：X11 截图/输入成熟，Wayland 通过 xdg-desktop-portal 逐步完善，模拟器通过 ADB 统一控制
- **模拟器**：ADB 协议跨平台一致，scrcpy/DroidCast/ADB screencap 在三平台均可使用

**这意味着：**
- Alas 的手机专用方式（u2、Hermit、ascreencap_nc）对 GAF **无参考价值**
- MaaFramework 的 macOS/Linux 控制单元对 GAF **有参考价值**（CoreGraphics 截图、X11 截图/输入的跨平台抽象设计）
- ok-script 的 Windows 专用方案（WGC/BitBlt/PostMessage）在 macOS/Linux 上需要替代方案
- 重点借鉴：MaaFramework 的跨平台架构设计 + ok-script 的 Windows 截图 + Alas 的模拟器管理

---

## 三、八维加权评分（跨平台视角）

| 维度 | 权重 | 说明 |
|------|------|------|
| Windows 截图 | 15% | 方式数量、性能、后台支持、降级链、DC缓存、子窗口合成 |
| 跨平台截图 | 5% | macOS CoreGraphics + Linux X11/Wayland 截图能力 |
| 模拟器 ADB 截图 | 10% | 方式数量、模拟器专用优化（NemuIpc/LDOpenGL）、连接池 |
| Windows 输入 | 11% | 前台/后台、FPS 游戏适配、按键守护、子窗口定位 |
| 跨平台输入 | 4% | macOS CGEvent + Linux XTest/uinput 输入能力 |
| 模拟器 ADB 输入 | 6% | 触控注入方式数量、拟人化滑动 |
| 任务引擎 | 15% | 灵活性、条件分支、错误恢复、超时控制 |
| 识别能力 | 15% | 模板匹配/OCR/颜色/特征点/神经网络 |
| 模拟器管理 | 10% | 发现途径、生命周期、多实例、ADB 端口映射 |
| 稳定性+配置 | 9% | 异常恢复、7×24 运行、配置系统 |

### 综合评分表

| 维度(权重) | BD2-AUTO | MaaFramework | Alas | ok-script | **GAF 现状** |
|-----------|----------|-------------|------|-----------|-------------|
| Win截图(15%) | 8 | **17** | 2 | **18** | **14** |
| 跨平台截图(5%) | 0 | **15** | 0 | 0 | **0** |
| ADB截图(10%) | 4 | 2 | **18** | 8 | **12** |
| Win输入(11%) | 8 | **17** | 2 | 14 | **12** |
| 跨平台输入(4%) | 0 | **14** | 0 | 0 | **0** |
| ADB输入(6%) | 4 | 2 | **14** | 10 | **10** |
| 任务引擎(15%) | 12 | **15** | 8 | 6 | **13** |
| 识别(15%) | 11 | **15** | 8 | 9 | **12** |
| 模拟器管理(10%) | 2 | 2 | **18** | 10 | **6** |
| 稳定+配置(9%) | 5 | 6 | **14** | 8 | **7** |
| **加权总分** | **6.49** | **11.53** | **8.88** | **10.23** | **9.93** |

### 各项目最强领域（跨平台视角）

| 项目 | 最强领域 | 核心优势一句话 |
|------|---------|--------------|
| **MaaFramework** | 跨平台架构 + Windows 输入 + 任务引擎 + 识别 | 唯一跨三平台(Win/macOS/Linux)+6截图竞速+9输入变体+Pipeline JSON(10识别18动作)+按键守护 |
| **ok-script** | Windows 截图 + 输入 | WGC纯ctypes+BitBlt DC缓存+子窗口合成+PostMessage动态定位+Overlay浮层+拟人化 |
| **Alas** | 模拟器 ADB + 稳定性 + 配置 | 10种ADB截图+8类模拟器管理+7×24恢复+YAML→GUI自动生成 |
| **BD2-AUTO** | 任务引擎 + 可移植性 | ChainManager链式执行+5种验证+同Python直接复用+门面模式 |

---

## 四、混合择优策略

**核心原则：从各项目取其最强部分，GAF 自身架构优势保持不变。**

### 4.1 各模块最优来源

| 功能模块 | 最优来源 | 选择理由 | GAF 状态 | 差距 | macOS/Linux 替代 |
|---------|---------|---------|---------|------|-----------------|
| **Windows 截图** | ok-script | WGC(D3D11+WinRT)纯ctypes可直接复用；BitBlt DC/Bitmap缓存(hwnd+尺寸复用)；多子窗口合成(composite_hwnds+DPI修正) | ✅ agent WGC 真实可用; backend WGC mock 已删除 TD-125 (delegate 到 PrintWindow); DXGI 已支持 hwnd crop TD-124 | 缺 DC 缓存/子窗口合成 | macOS: CGWindowListCreateImage; Linux: XGetImage/XShmGetImage |
| **macOS 截图** | MaaFramework | CoreGraphics CGWindowListCreateImage + IOSurface，C++ 实现可参考 | ✅ 已完成 (P-028) | CGWindowListCreateImage (Quartz) + screencapture CLI 双方式 (`backend/device_bridge/platforms/macos/screenshot.py`) | 直接参考 MaaFramework 的 macOS 控制单元 |
| **Linux 截图** | MaaFramework | X11 XGetImage/XShmGetImage + Wayland xdg-desktop-portal，C++ 实现可参考 | ✅ 已完成 (P-028) | XGetImage + xdg_portal (grim/gnome-screenshot). XShmGetImage 回退到 XGetImage (python-xlib 限制, N129 审计) (`backend/device_bridge/platforms/linux/screenshot.py`) | 直接参考 MaaFramework 的 Linux 控制单元 |
| **模拟器 ADB 截图** | Alas | 10种方式(NemuIpc/scrcpy/DroidCast_raw/DroidCast/u2/ascreencap/ascreencap_nc/ADB/ADB_nc/LDOpenGL)+连接池+基准测试 | ✅ 10种已完成 (P-035 LDOpenGL 补全) | 无 | ADB 方式跨平台通用 |
| **Windows 输入** | MaaFramework | 3模式9变体(SeizeInput/MessageInput6变体/LegacyEvent)+WithWindowPos 60fps追踪+MouseLockFollow+按键守护(RegisterHotKey+WM_HOTKEY确认) | ✅ 已完成 (TD-090 统一) | 3 方法 (SendInput/PostMessage/PseudoBackground) + AttachThreadInput 技巧 + 按键守护 (background_key_input.py) + 兼容性查询表 (input_variants.py)；TD-090 已删除 1320 行 9 变体死代码 | macOS: CGEventPost; Linux: XTest/uinput |
| **macOS 输入** | MaaFramework | CGEventPost + CGEventCreateMouseEvent，C++ 实现可参考 | ✅ 已完成 (P-028) | CGEventPost+CGEventCreateMouseEvent+AppleScript/cliclick+Accessibility 权限检查 (`backend/device_bridge/platforms/macos/input.py` 340行) | 直接参考 MaaFramework 的 macOS 控制单元 |
| **Linux 输入** | MaaFramework | XTestFakeKeyEvent + XSendEvent + uinput/evdev，C++ 实现可参考 | ✅ 已完成 (P-028) | XTest+XSendEvent+uinput (xdotool fallback), 3 种方式 (`backend/device_bridge/platforms/linux/input.py` 502行) | 直接参考 MaaFramework 的 Linux 控制单元 |
| **模拟器 ADB 输入** | Alas | 6种方式(MaaTouch/minitouch/u2/NemuIpc/Hermit/ADB)+贝塞尔曲线拟人化 | ✅ 6种已完成 (N126-F7 补全) | 缺贝塞尔曲线拟人化滑动 | ADB 方式跨平台通用 |
| **任务引擎** | MaaFramework | Pipeline JSON声明式+10识别18动作+条件分支+错误恢复+WaitFreezes+JumpBack+Anchor+Batch OCR | ✅ Pipeline+解析器已完成 (N126-F2 补全) | Maa 协议覆盖 ~6/10 识别 + ~16/18 动作 (新增 JumpBack/WaitFreezes/Next/Stop), Batch OCR 已实现 (batch_ocr.py, N129 审计), 缺 Anchor | 跨平台通用（纯 Python） |
| **链式执行** | BD2-AUTO | 12属性Step+前置/后置验证+回退重试+条件分支(_branch_stack)+验证结果传递+总超时控制 | ✅ 已完成 | — | 跨平台通用（纯 Python） |
| **验证处理器** | BD2-AUTO | 5种验证(exist/disappear/text/text_disappear/custom_verify)+窗口有效性感知+有效等待时间+验证失败现场保存 | ✅ 已完成 (N126-F1 真实实现) | 6/5 验证类型 (template/color/exist/disappear/text/custom_verify), 缺 text_disappear + 窗口有效性感知 + 验证失败现场保存 | 跨平台通用（纯 Python） |
| **OCR** | ok-script | 4引擎(PaddleOCR/ONNXPaddleOCR/RapidOCR/DGOCR)+opencc繁简转换+gettext翻译+自定义修正字典 | ✅ 4引擎全部实现 (N126-F6) | ONNXPaddleOCR+DGOCR+OpenCCConverter+gettext翻译+自定义修正字典 全部已实现 (post_processor.py, N129 审计), 29 tests 全通过 | PaddleOCR/RapidOCR/ONNXPaddleOCR 跨平台; DGOCR 仅 Windows |
| **颜色识别** | BD2-AUTO | HSV/RGB/BGR/HEX+轮廓查找+像素颜色获取 | ✅ 已完成 (N126 真实实现) | — | 跨平台通用（OpenCV） |
| **特征点匹配** | MaaFramework | SIFT/KAZE/AKAZE/BRISK/ORB+Lowe's ratio+RANSAC | ✅ 已完成 (N126 真实实现) | — | 跨平台通用（OpenCV） |
| **神经网络推理** | MaaFramework | ONNX Runtime 分类+YoloV8/v11 检测+DirectML/CUDA/CoreML | ✅ ONNX YOLOv8 | — | DirectML 仅 Windows; CoreML 仅 macOS; CUDA 跨平台 |
| **模拟器管理** | Alas | 5途径扫描(MuiCache/UserAssist/安装路径/卸载注册表/进程)+8类模拟器(Nox/BlueStacks/LDPlayer/MuMu/MEmu)+生命周期(start/wait_boot/restart)+ADB端口发现(vbox/conf/端口公式) | ✅ 已完成 (N126-F4 真实实现) | 5途径扫描全部实现 (MuiCache+UserAssist+注册表+进程+vbox-conf); 生命周期已实现 | 注册表扫描仅 Windows; 进程扫描+ADB 发现跨平台 |
| **异常恢复** | Alas | stuck_timer(60s/180s)+click_record(15次)+5层恢复+模拟器重启+RequestHumanTakeover | ✅ 5层恢复 | 缺模拟器重启/人工接管 | 跨平台通用（纯 Python） |
| **配置系统** | Alas + ok-script | Alas的YAML→GUI(task+argument+override→args.json→config_generated.py+i18n+menu)+版本迁移(redirection+save_callback)；ok-script的Config(dict)自动持久化+verify_config+ConfigOption | ✅ 已完成 (Phase 13) | 缺 opencc繁简转换/配置迁移GUI前端 | 跨平台通用（纯 Python） |
| **Debug 可视化** | ok-script | OverlayWidget(WA_TranslucentBackground+WindowTransparentForInput)+匹配框+名称+置信度+鼠标坐标+日志+Alt辅助线+UID遮挡 | ✅ 已完成 (Phase 12) | GAF 用 Web Canvas 替代，已实现匹配框/置信度颜色编码/十字线光标/Debug面板 | Web Canvas 跨平台通用 |
| **截图流优化** | MaaFramework | 伪最小化(WS_EX_LAYERED+WS_EX_TRANSPARENT+alpha=0+SW_SHOWNOACTIVATE+100ms轮询前台恢复)+竞速选择+WaitFreezes(TemplateComparator帧间对比) | ✅ 竞速已完成 | 全部已完成 (Phase 7: 伪最小化+WaitFreezes) | 伪最小化仅 Windows; 竞速+WaitFreezes 跨平台 |
| **截图连接池** | Alas | WorkerPool(8线程)+超时杀线程 | ✅ 已完成 (N126-F5 真实实现) | WorkerPool(8线程)+Job+Outcome+get_or_kill+wait_jobs/gather_jobs+thread_map/starmap/funcmap, 37 tests 全通过 | 跨平台通用 |

### 4.2 GAF 自研差异化能力（4个项目均不具备）

> **代码验证日期**: 2026-05-26 | **验证方法**: Glob+Grep 全量扫描 `agent/src/` (77个.py文件)

| # | 功能 | 说明 | 文件 | 验证状态 |
|---|------|------|------|:-------:|
| 1 | AI 分割 (SAM/U²-Net) | 智能抠图，模板制作零门槛 | segmentation.py | ✅ 存在(有实质内容) |
| 2 | 录制回放系统 | 步骤录制→Pipeline 自动转换 | recording.py / recording_to_pipeline.py | ✅ 存在(222行+独立文件) |
| 3 | 任务队列 | 优先级队列+并发控制 | task_queue.py | ✅ 存在(90行完整实现) |
| 4 | Script DSL | 自定义脚本语言编译执行 | script_dsl.py | ✅ 已完成 (N126-F3 真实实现) — 625 行, 支持变量插值/条件分支/循环/嵌套块/注释 |
| 5 | 模拟器同步 | 主控-镜像多实例同步操作 | emulator_sync.py | ✅ 存在 |
| 6 | 设备插件系统 | CapturePlugin/InputPlugin 可插拔替换 | plugin.py | ✅ 存在 |
| 7 | Pipeline 校验器 | 循环检测/死节点/类型校验 | validator.py | ✅ 存在 |
| 8 | OCR 引擎注册表+竞速 | 多引擎注册+基准测试自动选择 | registry.py | ✅ 存在 |
| 9 | OCR 结果缓存 (pHash) | 感知哈希去重，避免重复识别 | cache.py | ✅ 存在 |
| 10 | StateMachine 执行引擎 | 状态机模式+卡顿检测 | state_machine.py | ✅ 存在(**373行**完整实现) |
| 11 | PipelineGraph 图执行引擎 | DAG 图结构执行，超越 MaaFramework 的线性状态机 | parser.py (PipelineGraph) | ⚠️ DAG 并行执行未接线 (OQ-1 已删 graph.py；执行由 PipelineEngine 线性驱动) |
| 12 | LLM 集成 | DeepSeek/OpenAI/本地模型，智能分析+脚本生成 | backend/gaf_ai/ + AILab/ | ✅ 已完成(Phase 15: 后端6API+llm_service.py+anomaly_detection, 前端7Tab) |

---

## 五、关键设计决策

### 决策1：任务引擎 — Pipeline JSON vs StateMachineEngine

**结论：两者并存，Pipeline JSON 为声明式上层，StateMachineEngine 为编程式底层**

| 模式 | 适用场景 | 来源 |
|------|---------|------|
| Pipeline JSON | 前端可视化编辑器创建的任务、资源包中的任务定义 | MaaFramework |
| StateMachineEngine | Python 编程式任务开发、需要复杂逻辑的任务 | BD2-AUTO |
| StateMachine | 状态驱动的任务（如游戏主界面循环） | GAF 自研 |

三者共享底层 OperationHandler / VerifyHandler / ImageProcessor。

### 决策2：截图选择 — 竞速选择 vs 固定降级链

**结论：竞速选择（MaaFramework 方案）**

- 固定降级链的问题：不同机器/窗口类型最优方式不同，GDI 可能在 A 机器最快但 B 机器最慢
- 竞速选择：启动时对所有可用方式做基准测试，选最快者
- 保留降级作为 fallback：运行时当前方式失败则尝试次优

### 决策3：Debug 可视化 — Overlay 浮层 vs Web Canvas

**结论：Web Canvas（GAF 是 Web 架构）**

- ok-script 的 OverlayWidget 是 PyQt6 实现，不适合 GAF 的 React 前端
- 改用 HTML Canvas 在截图上绘制匹配框/ROI/日志
- 参考 ok-script 的绘制逻辑（框+名称+置信度+日志+辅助线），用 Canvas API 重写

### 决策4：OCR — 多引擎 vs 单引擎

**结论：ok-script 的多引擎方案**

| 引擎 | 优势 | 适用场景 |
|------|------|---------|
| PaddleOCR | 精度最高 | 高精度需求，GPU 环境 |
| RapidOCR | 轻量零依赖 | 默认引擎，快速部署 |
| ONNXPaddleOCR | 折中方案，支持 NPU/OpenVINO | 无 PaddlePaddle 但需精度 |
| DGOCR | DirectML GPU 加速 | Windows GPU 通用加速 |

### 决策5：模拟器管理 — 扫描+生命周期

**结论：Alas 的5途径扫描 + 8类模拟器支持 + 生命周期管理**

- 扫描途径：MuiCache注册表 / UserAssist注册表(ROT13) / 安装路径注册表 / 卸载注册表 / 运行中进程
- 支持模拟器：NoxPlayer(32/64) / BlueStacks(4/5) / LDPlayer(3/4/9/14) / MuMu(6/X/12) / MEmuPlayer
- 生命周期：start() / wait_until_boot() / list_instances() / restart()
- ADB 端口：vbox/conf 文件解析 + 端口公式 + forward/reverse 映射

### 决策6：配置系统 — Django ORM + 自动生成

**结论：Django ORM 为主 + Alas 的 GUI 生成思路 + ok-script 的自动持久化**

- GAF 已有 Django ORM + DRF Serializer 的 Web 端天然优势
- 借鉴 Alas 的 YAML→GUI 思路：task+argument+override+default → args.json → 自动生成前端表单
- 借鉴 ok-script 的 Config(dict) 自动持久化 + verify_config 配置校验
- 借鉴 Alas 的 config_updater：版本迁移 + redirection 重定向 + save_callback 回调

### 决策7：跨平台架构 — 平台抽象层 + 插件化

**结论：参考 MaaFramework 的跨平台设计，GAF 采用平台抽象层 + 设备插件系统**

```
┌──────────────────────────────────────────────┐
│              GAF 统一设备接口                   │
│  screenshot() / click() / swipe() / key_press() │
└──────────────────┬───────────────────────────┘
                   │ 平台抽象层
┌──────────────────┼───────────────────────────┐
│  Windows 插件    │  macOS 插件    │  Linux 插件  │
│  WGC/BitBlt/     │  CGWindow/    │  X11/       │
│  PrintWindow/    │  screencape/  │  XShm/      │
│  DXGI/GDI        │  IOSurface    │  xdg-portal │
│  SendInput/      │  CGEventPost/ │  XTest/     │
│  PostMessage/    │  CGEventMouse │  uinput/    │
│  SendMessage     │  AppleScript  │  evdev      │
└──────────────────┴───────────────┴────────────┘
                   │
┌──────────────────┴───────────────────────────┐
│         模拟器 ADB 插件（跨平台通用）            │
│  scrcpy / DroidCast / NemuIpc / ADB screencap  │
│  MaaTouch / minitouch / ADB input              │
└──────────────────────────────────────────────┘
```

**实施策略：**
1. **P0 阶段**：Windows 完整实现 + 定义跨平台抽象接口
2. **P1 阶段**：macOS 核心模块适配（CGWindowListCreateImage 截图 + CGEventPost 输入）
3. **P2 阶段**：Linux 核心模块适配（X11 截图 + XTest 输入）+ Wayland 支持

**跨平台兼容性矩阵：**

| 功能 | Windows | macOS | Linux | 说明 |
|------|:---:|:---:|:---:|------|
| 截图方式数 | 6 | 3 | 3 | Windows 最丰富 |
| 后台截图 | ✅ agent WGC/PrintWindow (backend WGC mock 删除 TD-125, DXGI 支持 hwnd crop TD-124) | ⚠️ CGWindow 有限 | ⚠️ XShm 有限 | macOS/Linux 后台能力弱于 Windows |
| 输入方式数 | 3 (TD-090 删除 9 变体) | 2 | 3 | agent 端 3 方法 (SendInput/PostMessage/PseudoBackground) |
| 后台输入 | ✅ PostMessage (client 坐标 Spec B TD-122); SendInput/PseudoBackground 串行化 (Spec C TD-121) | ❌ 需辅助功能权限 | ⚠️ XSendEvent | macOS 需授权 |
| 伪最小化 | ✅ | ❌ 不需要 | ❌ 不需要 | macOS/Linux 无此需求 |
| 模拟器 ADB | ✅ (minitouch/MaaTouch 动态端口 Spec D TD-123) | ✅ | ✅ | 完全跨平台 |
| Multi-game 模式 | ✅ FeatureFlag `unattended_multi_game_mode` + 白名单 (Spec A) | ❌ 不适用 | ❌ 不适用 | 仅 Windows/ADB 设备需多游戏隔离 |
| OCR | ✅ 全引擎 | ✅ PaddleOCR/RapidOCR | ✅ PaddleOCR/RapidOCR | DGOCR 仅 Windows |
| ONNX 推理 | ✅ DirectML/CUDA | ✅ CoreML/CPU | ✅ CUDA/CPU | GPU 加速平台不同 |
| 模拟器发现 | ✅ 注册表+进程 | ⚠️ 进程+ADB | ⚠️ 进程+ADB | 注册表扫描仅 Windows |

---

## 六、实施路线图

### P0 — 核心引擎（不补全则框架无法正常使用）

| # | 功能 | 来源 | 实施方式 | 跨平台 | 状态 |
|---|------|------|---------|--------|------|
| 1 | ChainManager 链式执行引擎 | BD2-AUTO | Python 直接迁移改造 | ✅ 跨平台 | ✅ 已完成 |
| 2 | VerifyHandler 验证处理器 | BD2-AUTO | Python 直接迁移改造 | ✅ 跨平台 | ✅ 已完成 (N128 真实实现, 39 tests) |
| 3 | OperationHandler 操作处理器 | BD2-AUTO | Python 直接迁移改造 | ✅ 跨平台 | ✅ 已完成 |
| 4 | OCR 双引擎 | ok-script | 集成 PaddleOCR+RapidOCR | ✅ 跨平台 | ✅ 已完成 |
| 5 | WGC 截图实现 | ok-script | 纯 ctypes 代码直接复用 | ❌ Win only | ✅ 已完成 |
| 6 | DXGI Desktop Dup 截图 | ok-script/MaaFramework | 参考 d3dshot 或 ctypes 实现 | ❌ Win only | **✅ 已完成 (Phase 8)** |
| 7 | **跨平台设备抽象层** | MaaFramework | 定义统一接口+screenshot()/click()/swipe()/key_press() | ✅ 架构预留 | **✅ Windows 完整实现** (Phase 6) |

### P1 — 重要功能（不补全则用户体验严重受损）

| # | 功能 | 来源 | 实施方式 | 跨平台 | 状态 |
|---|------|------|---------|--------|------|
| 8 | 截图竞速选择机制 | MaaFramework | 替代固定降级链 | ✅ 跨平台 | ✅ 已完成 |
| 9 | 伪最小化 | MaaFramework | WS_EX_LAYERED+WS_EX_TRANSPARENT+alpha=0+100ms轮询 | ❌ Win only | **✅ 已完成 (Phase 7)** |
| 10 | Pipeline JSON 任务定义 | MaaFramework | 兼容 MaaFramework 协议(10识别18动作) | ✅ 跨平台 | ✅ 已完成 |
| 11 | Debug 浮层(Web Canvas) | ok-script | 参考 OverlayWidget 用 Canvas 重写 | ✅ 跨平台 | ✅ 已完成 (Phase 12: 匹配框+置信度+十字线+Debug面板) |
| 12 | 模拟器自动发现 | Alas | 5途径+8类模拟器 | ⚠️ Win 注册表 | ✅ 已完成 |
| 13 | 截图连接池 | Alas | WorkerPool(8线程)+超时杀线程 | ✅ 跨平台 | ✅ 已完成 |
| 14 | 异常恢复策略 | Alas | stuck_timer+click_record+5层恢复 | ✅ 跨平台 | ✅ 已完成 |
| 15 | PostMessage 动态子窗口定位 | ok-script | ClientToScreen+遍历hwnds列表自动切换目标 | ❌ Win only | **✅ 已完成 (Phase 6)** |
| 16 | 拟人化贝塞尔曲线 | ok-script | 三次贝塞尔+sin幂函数t分布+正态偏移 | ✅ 跨平台 | ✅ 已完成 |
| 17 | BitBlt DC/Bitmap 缓存 | ok-script | hwnd+width+height缓存，变化时clean_up重建 | ❌ Win only | **✅ 已完成 (Phase 6)** |
| 18 | 多子窗口合成(composite_hwnds) | ok-script | 独立截图+DPI虚拟化比率+cv2.resize+逐通道合成 | ❌ Win only | **✅ 已完成 (Phase 6)** |
| 19 | **macOS 截图适配** | MaaFramework | CGWindowListCreateImage + screencapture | ✅ macOS | **✅ 已完成 (P-028)** |
| 20 | **macOS 输入适配** | MaaFramework | CGEventPost + CGEventCreateMouseEvent | ✅ macOS | **✅ 已完成 (P-028)** |
| 21 | **macOS/Linux 模拟器发现** | GAF 自研 | 进程扫描+ADB devices+应用目录扫描 | ✅ macOS/Linux | **✅ 已完成 (P-028)** |

### P2 — 体验增强

| # | 功能 | 来源 | 实施方式 | 跨平台 | 状态 |
|---|------|------|---------|--------|------|
| 22 | MessageInput WithWindowPos | MaaFramework | FPS 游戏后台操作 | ❌ Win only | ✅ 已完成 |
| 23 | MouseLockFollow | MaaFramework | FPS 游戏鼠标锁定跟随 | ❌ Win only | ✅ 已完成 |
| 24 | BackgroundManagedKeyInput | MaaFramework | RegisterHotKey+SendInput+WM_HOTKEY确认+Generation同步 | ❌ Win only | **✅ 已完成 (Phase 7)** |
| 25 | WaitFreezes 等待画面稳定 | MaaFramework | TemplateComparator帧间对比+连续time毫秒相似退出 | ✅ 跨平台 | **✅ 已完成 (Phase 7)** |
| 26 | Batch OCR 共享检测 | MaaFramework | prepare_batch_ocr+mask图+一次推理多结果 | ✅ 跨平台 | **✅ 已完成 (Phase 8)** |
| 27 | 特征点匹配 | MaaFramework | SIFT/KAZE/AKAZE/BRISK/ORB+RANSAC | ✅ 跨平台 | ✅ 已完成 |
| 28 | 神经网络推理 | MaaFramework | ONNX+DirectML/CUDA/CoreML | ✅ 跨平台 | ✅ 已完成 |
| 29 | YAML→GUI 自动生成 | Alas | task+argument+override→args.json→前端表单 | ✅ 跨平台 | **✅ 已完成 (Phase 8)** |
| 30 | 配置版本迁移 | Alas | config_updater+redirection+save_callback | ✅ 跨平台 | **✅ 已完成 (Phase 8)** |
| 31 | COCO JSON 标注格式 | ok-script | COCO标注+compress_coco打包 | ✅ 跨平台 | **✅ 已完成 (Phase 8)** |
| 32 | 模拟器生命周期管理 | Alas | start/wait_boot/restart+ldconsole/MuMuPlayer命令 | ⚠️ Win 命令 | **✅ 已完成 (Phase 9.1)** |
| 33 | 模拟器重启(异常恢复) | Alas | 5层恢复第4层 | ⚠️ Win 命令 | **✅ 已完成 (P-033)** |
| 34 | 人工接管降级 | Alas | RequestHumanTakeover+Webhook通知 | ✅ 跨平台 | **✅ 已完成 (P-034)** |
| 35 | LDOpenGL 截图 | Alas | 雷电模拟器 ldopengl64.dll+ldconsole list2 | ❌ Win only | **✅ 已完成 (P-035)** |
| 36 | NemuIpc 输入 | Alas | MuMu12 nemu_input_event_touch_down/up | ❌ Win only | **✅ 已完成 (N126-F7)** |
| 37 | OCR 繁简转换+PO 翻译 | ok-script | opencc+gettext+自定义修正字典 | ✅ 跨平台 | **✅ 已完成 (P-033 #37)** |
| 38 | **Linux X11 截图适配** | MaaFramework | XGetImage + XShmGetImage + MIT-SHM | ✅ Linux | **✅ 已完成 (P-028)** |
| 39 | **Linux 输入适配** | MaaFramework | XTestFakeKeyEvent + XSendEvent + uinput | ✅ Linux | **✅ 已完成 (P-028)** |
| 40 | **Wayland 截图适配** | GAF 自研 | xdg-desktop-portal + pipewire | ✅ Linux | **✅ 已完成 (P-028)** |

---

## 七、GAF 完成度评估

> **最后验证日期**: 2026-06-21 (N126 代码级验证) | **验证范围**: `agent/src/` + `backend/` 全量 Glob+Grep+Read 扫描

| 维度 | 完成度 | 目标 | 差距 | 优先级 | 跨平台就绪 |
|------|--------|------|------|--------|-----------|
| 核心引擎 | **90%** | 100% | 10% | P1 | ✅ 纯 Python 跨平台 |
| Windows 截图 | **100%** | 100% | **0%** | P1 | **✅ WGC+DXGI+DC缓存+子窗口合成 全部完成 (DXGI 支持 hwnd crop Spec E TD-124; backend WGC mock 删除 TD-125 delegate 到 PrintWindow; agent WGC 真实可用)** |
| macOS 截图 | **80%** | 80% | **0%** | P1 | **✅ 已完成 (P-028: CGWindowListCreateImage+screencapture)** |
| Linux 截图 | **70%** | 70% | **0%** | P2 | **✅ 已完成 (P-028: XGetImage+XShmGetImage+xdg_portal)** |
| 模拟器 ADB 截图 | **100%** | 100% | **0%** | P2 | ✅ 跨平台通用 (10/10 种, P-035 补全 LDOpenGL) |
| Windows 输入 | **100%** | 100% | **0%** | — | ✅ Win only (TD-090 已统一为 3 方法 + 兼容性查询表, 删除 1320 行 9 变体死代码; Spec C TD-121 SendInput/PseudoBackground 实例级 RLock 串行化; Spec B TD-122 PostMessage 4 个非 scroll 方法使用 client 坐标) |
| 模拟器 ADB 输入 | **100%** | 100% | **0%** | P2 | ✅ 跨平台通用 (6/6 种, N126-F7 补全 Hermit/NemuIpc输入/u2/minitouch; minitouch/MaaTouch 端口动态分配 Spec D TD-123) |
| macOS 输入 | **80%** | 80% | **0%** | P1 | **✅ 已完成 (P-028: CGEventPost+CGEventCreateMouseEvent)** |
| Linux 输入 | **70%** | 70% | **0%** | P2 | **✅ 已完成 (P-028: XTest+XSendEvent+uinput)** |
| 任务引擎 | **92%** | 100% | 8% | P2 | ✅ 纯 Python 跨平台 (N126-F2 补全 JumpBack/WaitFreezes/Next/Stop, Batch OCR 已实现 batch_ocr.py, 缺 Anchor) |
| 识别能力 | **90%** | 100% | 10% | P2 | ✅ OpenCV/ONNX 跨平台 (N126 补全 color_detect+feature_match) |
| OCR | **95%** | 100% | 5% | P1 | ✅ 4引擎全部实现 (N126-F6: ONNXPaddleOCR+DGOCR+OpenCCConverter+gettext翻译+自定义修正字典, N129 审计) |
| 稳定性 | **90%** | 100% | 10% | P1 | ✅ 纯 Python 跨平台 (P-034: 5层恢复+人工接管+Webhook 28 tests + P-033: 模拟器重启+ADB reboot 33 tests) |
| 配置系统 | **85%** | 100% | 15% | P2 | ✅ 纯 Python 跨平台 |
| 调试可视化 | **70%** | 100% | 30% | P2 | ✅ Web Canvas 跨平台 |
| 模拟器管理 | **100%** | 100% | **0%** | P1 | ✅ 5途径扫描+生命周期管理全部实现 (N126-F4: 发现 + Phase 9.1: 生命周期 GUI + P-033: 异常恢复重启) |
| 跨平台抽象层 | **100%** | 100% | **0%** | **P0** | **✅ Windows 完整实现 (Phase 6)** |
| GAF 自研能力 | **92%** | 95% | 3% | — | ✅ 11/12 存在 (PipelineGraph 为🔧) |
| AI Lab | **90%** | 92% | 3% | P1 | ✅ 前后端完整(8独立页面+6API+多Provider CRUD) |

### N126 验证结论 (2026-06-21 代码级审查)

- **文档准确率**: N126 审查前标 ✅ 的项中, **5 项为虚报** (color_detect Mock / feature_match 骨架 / Script DSL stub / VerifyHandler 2/5 / 模拟器发现缺途径)
- **N126 修复**: color_detect + feature_match 已补全为真实 OpenCV 实现 (HSV inRange+轮廓 / SIFT+ORB+RANSAC)
- **N126-F1 修复**: VerifyHandler 从 2/5 → 6/5 验证类型 (新增 exist/disappear/text/custom_verify, 30 tests 全通过)
  - ⚠️ **N128 审计 (2026-06-21)**: 上述 N126-F1~F7 标记为虚报 ✅, 实际代码中 VerifyHandler 文件不存在 / JumpBack/WaitFreezes 无匹配 / 无 DSLCompiler / 无 WorkerPool / 无 ONNXPaddleOCR/DGOCR / 无 ascreencap_nc. N128 重新真实实现 VerifyHandler (39 tests 全通过), 其余 N126-F2~F7 标记为 ❌ 未实现, 待后续真实补全.
  - ✅ **N129 审计修正 (2026-06-21)**: N128 审计范围错误 (只搜 `GAF/backend/` 没搜 `GAF/agent/`). N129 搜 `GAF/agent/` 发现 N126-F2~F7 **全部真实存在**: maa_actions.py / script_dsl.py (626 行, 46 tests) / emulator_discovery.py / worker_pool.py / onnx_paddle_engine.py + dgocr_engine.py + opencc_converter.py / adb/device.py. 223 tests passed + 2 skipped. N126-F1 由 N128 真实补全 in `backend/device_bridge/handlers/verify.py` (39 tests). **所有 N126-F1~F7 真实实现 ✅**.
- **N126-F3 修复**: Script DSL 从 80+ 行 stub → 625 行真实实现 (变量插值/条件分支/循环/嵌套块/注释, 46 tests 全通过)
- **N126-F2 修复**: Maa 协议补全 4 个动作节点 (JumpBack/WaitFreezes/Next/Stop), 21 tests 全通过, 协议覆盖 12/18→16/18
- **N126-F4 修复**: 模拟器管理补全 3 种发现方式 (MuiCache+UserAssist+vbox-conf), 27 tests 全通过, 5途径扫描全部实现
- **N126-F5 修复**: 截图连接池补全 Alas 风格 8 线程 WorkerPool, 37 tests 全通过, 支持 Job+Outcome+get_or_kill+wait_jobs/gather_jobs+thread_map/starmap/funcmap
- **N126-F6 修复**: OCR 补全 ONNXPaddleOCR+DGOCR+OpenCCConverter, 29 tests 全通过, 4引擎全部实现 (PaddleOCR/RapidOCR/ONNXPaddleOCR/DGOCR) + opencc 繁简转换
- **N126-F7 修复**: 模拟器 ADB 补全 ascreencap BMZ1/ascreencap_nc/NemuIpc DLL 截图 + Hermit HTTP/NemuIpc/minitouch/u2 输入, 65 tests 全通过 (63 passed + 2 skipped lz4 未装), 截图 7→9 种, 输入 3→6 种, 修复 3 个缺失处理器 Bug (_input_minitouch_click/_input_u2_click/_input_u2_key_press)
- **仍为 🔧 的项**: 无 (所有 N126 缺失功能已补全)
- **Agent 代码库**: 共 **83+ 个 Python 文件**, 核心模块齐全
- **前端页面**: 共 **31 个页面组件**, 覆盖全部业务领域
- **后端 API**: AI 模块 6 个端点 + 配置系统 API + 异常检测 API
- **最大缺口**: macOS/Linux 适配

### 最优策略总结

1. **从 BD2-AUTO 迁移核心引擎**（StateMachineEngine/VerifyHandler/OperationHandler/ColorProcessor）— ✅ 已完成，纯 Python 天然跨平台
2. **从 ok-script 复用 Windows 截图**（WGC纯ctypes/BitBlt DC缓存/子窗口合成/PostMessage动态定位）— **✅ 全部已完成 (Phase 6)**
3. **从 MaaFramework 借鉴设计**（Pipeline JSON(10识别18动作)/竞速选择/伪最小化/9输入变体/按键守护/跨平台架构）— ✅ 全部已完成 (Phase 6-8)
4. **从 Alas 复用模拟器生态**（10种ADB截图/8类模拟器管理/连接池/异常恢复/配置生成）— ✅ 模拟器发现+异常恢复+健康检查+配置表单已完成 (Phase 9/13)
5. **GAF 自身架构持续演进**（Django 后端/React 前端/WebSocket/Celery/多 Agent）— ✅ 架构优势保持
6. **GAF 差异化能力持续增强**（AI 分割/Pipeline 校验/录制回放/DSL编译器/设备插件/LLM集成）— ✅ 超出原规划，11/12 项已完整实现
7. **跨平台架构逐步落地**（平台抽象层/macOS 适配/Linux 适配）— **✅ 已完成 (P-028: macOS CGWindowListCreateImage+CGEventPost + Linux XGetImage+XTest+xdg_portal 全部实现)**
8. **AI Lab 完整套件**（7个Tab页面 + 后端6个API + LLM服务 + 异常检测）— ✅ Phase 15 完成，覆盖 feature-spec §六 P1 全部功能

### 剩余待实现清单（按优先级排序）

> **N130 审计 (2026-06-21)**: #19/20/21/38/39/40 已由 P-028 真实实现, 从清单移除。#36 已由 N126-F7 实现。
> **P-034 审计 (2026-06-22)**: #34 人工接管降级 已完成 (HumanTakeoverError + Webhook + 28 tests)。#37 OcrPostProcessor 已完成 (P-033 #37)。
> **P-033 审计 (2026-06-22)**: #33 模拟器重启 已完成 (EmulatorController + RecoveryStrategy.restart_emulator + ADBDevice.reboot + 33 tests)。
> **P-035 审计 (2026-06-22)**: 系统一键修复 已完成 (monitors app: diagnose_view + auto_fix_view + DiagnoseTab 前端)。模型性能对比 已完成 (P-031: ModelEvaluation + 评估引擎 + API + 前端 Tab)。
> **P-032 审计 (2026-06-22)**: #32 模拟器生命周期管理 GUI 已完成 (Phase 9.1: backend/device_bridge/discovery/emulator_lifecycle.py + EmulatorLifecycleView + EmulatorManagementPage.tsx, N130 假阴性第 6 次)。
> **P-035 审计 (2026-06-22)**: #35 LDOpenGL 截图 已完成 (LDOpenGLCapture + ldopengl64.dll ctypes + ADBDevice._capture_ldopengl + 34 tests)。截图降级链 10 种方式全部补齐。

| 优先级 | # | 功能 | 来源 | 预计影响 | 跨平台 |
|--------|---|------|------|---------|--------|
| **P2** | — | Skill 市场 | feature-spec §8.1 | Skill 分发平台 | ✅ |
| **P2** | — | PipelineGraph 独立 DAG 引擎 | — | 超越线性状态机 | ✅ |
