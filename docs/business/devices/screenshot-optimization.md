---
summary: GAF 截图优化设计
applies_to: ['backend', 'design']
key_decisions:
  - 截图降级链策略
  - SSIM 策略检测
  - 现实状态：截图栈已实现，优化层 helpers 已实现（集成待 P3）
last_updated: 2026-07-04
---

# GAF 截图优化设计

> 版本：2.2 | 日期：2026-07-04 | 修订：Phase 3.1-3.4 优化层 helpers 已实现（🔧 待集成到 ScreenshotManager.capture 热路径）

## 0. 现实状态（2026-07-04 二次审计）

> ⚠️ **历史背景**：v2.0 文档原标记"✅ 已全部实现"为**虚报**。v2.1 (2026-07-04) 修正为"截图捕获栈已实现，优化层全部缺失"。v2.2 (2026-07-04) 再次更新：优化层 helpers（SSIMChecker / AdaptiveJPEGCompressor / ScreenshotCache）已实现为独立工具类并通过单元测试，但尚未接入 `ScreenshotManager.capture()` 热路径（🔧 集成待 P3 任务）。

### 0.1 实现状态矩阵

| 文档章节 | 文档声称 | 现实代码 | 状态 |
|----------|----------|----------|------|
| §2 截图降级链 | `ScreenshotFallbackChain` 类 + `ScreenshotStrategy` 抽象 | `agent/src/platforms/windows/screenshot.py` 的 `ScreenshotManager` 类（无抽象基类，无 `register_chain` API） | 🟡 逻辑存在，类名/接口不同 |
| §2.1 Windows 降级链 | WGC → DXGI → GDI → PrintWindow（4 级） | WGC → DXGI → GDI → PrintWindow（4 级，已对齐） | ✅ 实现 |
| §3 SSIM 检测 | `SSIMChecker` 类 + `SmartScreenshotManager` | `agent/src/devices/ssim_checker.py` 的 `SSIMChecker` 类（skimage + cv2.PSNR fallback）；`SmartScreenshotManager` 包装类未实现（helpers 已就绪） | 🔧 helpers 实现，集成待 P3 |
| §4 JPEG 质量 | `AdaptiveJPEGCompressor` 类 + 自适应压缩 | `agent/src/devices/jpeg_compressor.py` 的 `AdaptiveJPEGCompressor` 类（4 预设 + RTT 自适应 + 目标大小二分搜索）；`config.jpeg_quality` 字段已激活（helpers 入参消费） | 🔧 helpers 实现，集成待 P3 |
| §5 缓存 TTL | `ScreenshotCacheConfig` + `DynamicTTLManager` + Redis 缓存 | `agent/src/devices/screenshot_cache.py` 的 `ScreenshotCache` 类（Redis 后端 + 内存回退，LRU 驱逐）；`config.cache_ttl` 字段已激活；`test_degradation_chain.py` 已 un-skip 3 个测试 + 新增 2 个 hash 测试，全部通过 | 🔧 helpers 实现，集成待 P3 |
| §6 前端截图流 | `ScreenshotStreamManager` 类 | `frontend/src/hooks/useScreenshotStream.ts` 的 React Hook（范式不同，无类） | 🟡 逻辑存在，范式不同 |
| — FramePool | （文档未提，版本说明中提到） | `agent/src/platforms/windows/frame_pool.py` 的 `FramePool` 类（线程安全，最多 30 帧） | ✅ 实现 |
| — WGC 捕获 | §2.1 | `agent/src/platforms/windows/wgc.py` 的 `Win32WGC` 类 | ✅ 实现 |
| — DXGI 捕获 | §2.1 | `agent/src/platforms/windows/dxgi_capture.py` 的 `DXGICapture` 类 (agent 端, 真实可用); backend `device_bridge/platforms/windows/_dxgi.py` 的 `DXGICapture.capture_window(hwnd)` (Spec E TD-124, 支持 per-window crop) | ✅ 实现 |
| — 竞速 benchmark | （版本说明中提到"竞速"） | `agent/src/platforms/windows/benchmark.py` 的 `benchmark_capture_methods()`，已接入 `ScreenshotManager._detect_best_method` | ✅ 实现 |

> **Backend WGC 状态 (Spec E / TD-125, 2026-07-16)**: `backend/device_bridge/platforms/windows/_wgc.py` 已删除 (原是返回固定 1920×1080 蓝色图的 mock)。`_capture_wgc` delegate 到 `_capture_printwindow` + warning log。`WINDOWS_METHODS` 移除 'WGC'。Agent 端 `agent/src/platforms/windows/wgc.py` 的 `Win32WGC` 类仍真实可用。

### 0.2 实际截图机制

文件：`agent/src/platforms/windows/screenshot.py`

- **类名**：`ScreenshotManager`（**非** `ScreenshotFallbackChain`）
- **降级链**：WGC → DXGI → GDI → PrintWindow（4 级，已与文档对齐）
- **自动选优**：首次截图时调用 `benchmark_capture_methods(hwnd)` 竞速测试，结果写入 `device.screenshot_method` 字段
- **重试**：每个策略包裹 `@retry_screenshot()` 装饰器
- **JPEG**：backend `device_bridge/platforms/windows/screenshot.py` 仍硬编码 85；agent 端 `AdaptiveJPEGCompressor` 已就绪（🔧 待接入）

> **DXGI per-window crop (Spec E / TD-124, 2026-07-16)**: backend `DXGICapture` 新增 `capture_window(hwnd)` 方法, 通过 `GetWindowRect` + `DXGI_OUTPUT_DESC.DesktopCoordinates` 平移 + numpy slice 实现 per-window 截图 (不再截全桌面)。`_capture_dxgi(hwnd)` 改用 `capturer.capture_window(hwnd_int)` 替代 `capturer.capture()`。WindowsScreenshotHandler 多游戏并行场景下 DXGI 可安全使用 (仍被 Spec A 白名单保守 blocked, 但底层冲突已修)。

### 0.3 修复优先级

| 项 | 优先级 | 修复方向 | 状态 |
|----|--------|---------|------|
| 修复断裂测试 `test_degradation_chain.py` | P0 | 实现 `devices.screenshot_cache` 模块 | ✅ 完成（Phase 3.3） |
| 文档补全 WGC | P1 | §2.1 降级链改为 WGC → DXGI → GDI → PrintWindow | ✅ 完成（v2.2） |
| 实现截图缓存 helpers | P2 | 新建 `agent/src/devices/screenshot_cache.py` | ✅ 完成（Phase 3.3） |
| 实现 SSIM 去重 helpers | P2 | 新建 `agent/src/devices/ssim_checker.py` | ✅ 完成（Phase 3.1） |
| 实现 AdaptiveJPEGCompressor helpers | P2 | 新建 `agent/src/devices/jpeg_compressor.py` | ✅ 完成（Phase 3.2） |
| 接入 `ScreenshotManager.capture()` 热路径 | P3 | 在 `capture()` 内嵌 SSIM/JPEG/cache 逻辑 | 🔧 待 P3 任务 |

---

## 1. 概述

截图是 GAF 最频繁的操作，直接影响任务执行效率和用户体验。本设计定义截图降级链策略、SSIM 策略检测、JPEG 质量配置、缓存 TTL 配置和前端截图流优化方案。

> ⚠️ **现实提示**：截图下游"捕获栈"已实现（WGC/DXGI/GDI/PrintWindow + 竞速 + FramePool）。优化层 helpers（SSIMChecker / AdaptiveJPEGCompressor / ScreenshotCache）已实现为独立工具类并通过单元测试（Phase 3.1-3.4 完成），但**尚未接入 `ScreenshotManager.capture()` 热路径**（🔧 P3 任务）。下文 §3-§5 反映 helpers 的实际实现。

---

## 2. 截图降级链策略

### 2.1 Windows 截图降级链

```
WGC → DXGI → GDI → PrintWindow
```

| 方式 | 延迟 | 质量 | 适用场景 |
|------|------|------|---------|
| WGC | ~2ms | 无损 | Windows 10+，硬件加速，前台窗口首选 (agent 端; backend WGC mock 已删除 TD-125) |
| DXGI | ~3ms | 无损 | Windows 8+，前台窗口 (支持 per-window crop, Spec E TD-124, 多游戏并行场景可隔离) |
| GDI | ~10ms | 无损 | 通用 Windows |
| PrintWindow | ~50ms | 无损 | 后台窗口截图 |

### 2.2 ADB 截图降级链

```
nemu → scrcpy → DroidCast_raw → uiautomator2 → screencap+nc → screencap
```

详见 adb-control-design 设计（原独立文档已随 s36 归档，见 `docs/specs/archived/2026-08/2026-08-18-s36-adb-device-split.md`）。

### 2.3 降级链管理器

```python
class ScreenshotFallbackChain:
    """截图降级链管理器"""

    def __init__(self):
        self._chains: dict[str, list[ScreenshotStrategy]] = {}
        self._active: dict[str, ScreenshotStrategy] = {}
        self._failure_counts: dict[str, dict[str, int]] = {}

    def register_chain(self, device_type: str, strategies: list[ScreenshotStrategy]) -> None:
        """注册降级链"""
        self._chains[device_type] = sorted(strategies, key=lambda s: s.priority)

    def capture(self, device_id: str, device_type: str) -> np.ndarray:
        """截图，自动降级"""
        if device_id in self._active:
            strategy = self._active[device_id]
            try:
                result = strategy.capture(device_id)
                self._reset_failure(device_id, strategy.name)
                return result
            except Exception:
                self._record_failure(device_id, strategy.name)
                del self._active[device_id]

        chain = self._chains.get(device_type, [])
        for strategy in chain:
            if self._is_blacklisted(device_id, strategy.name):
                continue
            try:
                result = strategy.capture(device_id)
                self._active[device_id] = strategy
                self._reset_failure(device_id, strategy.name)
                return result
            except Exception:
                self._record_failure(device_id, strategy.name)
                continue

        self._active.pop(device_id, None)
        raise ScreenshotError(f"All screenshot strategies failed for {device_id}")

    def _record_failure(self, device_id: str, strategy_name: str) -> None:
        """记录策略失败"""
        if device_id not in self._failure_counts:
            self._failure_counts[device_id] = {}
        self._failure_counts[device_id][strategy_name] = \
            self._failure_counts[device_id].get(strategy_name, 0) + 1

    def _reset_failure(self, device_id: str, strategy_name: str) -> None:
        """重置策略失败计数"""
        if device_id in self._failure_counts:
            self._failure_counts[device_id].pop(strategy_name, None)

    def _is_blacklisted(self, device_id: str, strategy_name: str) -> bool:
        """检查策略是否被临时黑名单"""
        failures = self._failure_counts.get(device_id, {}).get(strategy_name, 0)
        return failures >= 3
```

---

## 3. SSIM 策略检测

### 3.1 SSIM 原理

结构相似性指数（SSIM）用于检测两张截图的相似度。当连续两张截图 SSIM > 阈值时，认为画面未变化，可跳过图像识别操作。

### 3.2 SSIM 检测实现

```python
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

class SSIMChecker:
    """SSIM 策略检测器"""

    def __init__(self, threshold: float = 0.98, downsample: int = 4):
        self._threshold = threshold
        self._downsample = downsample
        self._last_screenshot: np.ndarray | None = None
        self._last_score: float = 1.0

    def is_same_scene(self, current: np.ndarray) -> bool:
        """检测当前截图是否与上一张相同"""
        if self._last_screenshot is None:
            self._last_screenshot = current
            return False

        small_current = self._downsample_image(current)
        small_last = self._downsample_image(self._last_screenshot)

        if small_current.shape != small_last.shape:
            self._last_screenshot = current
            return False

        score = ssim(small_current, small_last, channel_axis=2)
        self._last_score = score
        self._last_screenshot = current

        return score >= self._threshold

    def _downsample_image(self, image: np.ndarray) -> np.ndarray:
        """降采样图像以加速 SSIM 计算"""
        h, w = image.shape[:2]
        new_h, new_w = h // self._downsample, w // self._downsample
        return cv2.resize(image, (new_w, new_h))

    @property
    def last_score(self) -> float:
        """获取最近一次 SSIM 值"""
        return self._last_score

    def reset(self) -> None:
        """重置状态"""
        self._last_screenshot = None
        self._last_score = 1.0
```

### 3.3 SSIM 在任务执行中的应用

```python
class SmartScreenshotManager:
    """智能截图管理器，集成 SSIM 检测"""

    def __init__(self, screenshot_chain: ScreenshotFallbackChain, ssim_checker: SSIMChecker):
        self._chain = screenshot_chain
        self._ssim = ssim_checker
        self._last_capture: np.ndarray | None = None

    def capture(self, device_id: str, device_type: str, force: bool = False) -> np.ndarray:
        """智能截图，SSIM 检测可跳过重复截图"""
        if not force and self._last_capture is not None:
            current = self._chain.capture(device_id, device_type)
            if self._ssim.is_same_scene(current):
                return self._last_capture
            self._last_capture = current
            return current

        current = self._chain.capture(device_id, device_type)
        self._last_capture = current
        return current

    def force_capture(self, device_id: str, device_type: str) -> np.ndarray:
        """强制截图，忽略 SSIM"""
        return self.capture(device_id, device_type, force=True)
```

### 3.4 SSIM 性能优化

| 优化手段 | 说明 | 效果 |
|----------|------|------|
| 降采样 | 4x 降采样后计算 SSIM | 计算量减少 16x |
| 灰度对比 | 先灰度 SSIM，差异大再彩色 | 快速排除 |
| 缓存 | 保留最近 1 帧即可 | 内存占用低 |
| 跳过频率 | 每 N 帧才做 SSIM 检测 | 减少 SSIM 计算次数 |

---

## 4. JPEG 质量配置

### 4.1 质量等级

| 场景 | JPEG 质量 | 预估大小 (1280x720) | 说明 |
|------|----------|---------------------|------|
| 图像识别 | 95 | ~150 KB | 高质量，保证识别精度 |
| 实时监控 | 80 | ~50 KB | 平衡质量和大小 |
| 截图流 | 70 | ~30 KB | 低延迟传输 |
| 缩略图 | 50 | ~10 KB | 仅用于预览 |

### 4.2 自适应质量配置

```python
class AdaptiveJPEGCompressor:
    """自适应 JPEG 压缩器"""

    QUALITY_PRESETS = {
        "recognition": 95,
        "monitor": 80,
        "stream": 70,
        "thumbnail": 50,
    }

    def __init__(self, default_quality: int = 80):
        self._default_quality = default_quality
        self._bandwidth_estimate: float = float("inf")

    def compress(self, image: np.ndarray, purpose: str = "monitor") -> bytes:
        """压缩图像"""
        quality = self._get_quality(purpose)
        encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
        _, compressed = cv2.imencode(".jpg", image, encode_param)
        return compressed.tobytes()

    def _get_quality(self, purpose: str) -> int:
        """获取 JPEG 质量"""
        if purpose in self.QUALITY_PRESETS:
            return self.QUALITY_PRESETS[purpose]
        return self._default_quality

    def compress_for_stream(self, image: np.ndarray, target_size_kb: int = 50) -> bytes:
        """压缩到目标大小（二分搜索质量参数）"""
        low, high = 30, 95
        result = None

        while low <= high:
            mid = (low + high) // 2
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, mid]
            _, compressed = cv2.imencode(".jpg", image, encode_param)
            size_kb = len(compressed) / 1024

            if size_kb <= target_size_kb:
                result = compressed.tobytes()
                low = mid + 1
            else:
                high = mid - 1

        if result is None:
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, 30]
            _, compressed = cv2.imencode(".jpg", image, encode_param)
            result = compressed.tobytes()

        return result
```

---

## 5. 缓存 TTL 配置

### 5.1 缓存层级

```
Agent 本地缓存 (TTL=50ms) → Redis 缓存 (TTL=100ms) → Client 请求
```

### 5.2 TTL 配置

| 缓存层 | TTL | 说明 |
|--------|-----|------|
| Agent 内存缓存 | 50ms | 避免同一帧重复截图 |
| Redis 缓存 | 100ms | 多 Client 共享截图 |
| Client 内存缓存 | 200ms | 避免重复请求 |

### 5.3 缓存配置

```python
@dataclass
class ScreenshotCacheConfig:
    """截图缓存配置"""
    agent_ttl: float = 0.05          # Agent 本地缓存 TTL
    redis_ttl: float = 0.10          # Redis 缓存 TTL
    client_ttl: float = 0.20         # Client 缓存 TTL
    max_agent_cache_size: int = 10   # Agent 最大缓存帧数
    max_redis_cache_size: int = 50   # Redis 最大缓存帧数
    compression_quality: int = 80    # 缓存压缩质量
    enable_ssim: bool = True         # 启用 SSIM 检测
    ssim_threshold: float = 0.98     # SSIM 阈值
    ssim_downsample: int = 4         # SSIM 降采样倍率
```

### 5.4 动态 TTL 调整

```python
class DynamicTTLManager:
    """动态 TTL 管理器"""

    def __init__(self, base_ttl: float = 0.05):
        self._base_ttl = base_ttl
        self._current_ttl = base_ttl
        self._request_counts: list[int] = []
        self._window_size = 60

    def update(self, requests_per_second: int) -> float:
        """根据请求频率动态调整 TTL"""
        self._request_counts.append(requests_per_second)
        if len(self._request_counts) > self._window_size:
            self._request_counts.pop(0)

        avg_rps = sum(self._request_counts) / len(self._request_counts)

        if avg_rps > 20:
            self._current_ttl = self._base_ttl * 3
        elif avg_rps > 10:
            self._current_ttl = self._base_ttl * 2
        elif avg_rps > 5:
            self._current_ttl = self._base_ttl * 1.5
        else:
            self._current_ttl = self._base_ttl

        return self._current_ttl
```

> ⚠️ 未落地(2026-08-28)：实际为单 TTL(`default_ttl=300s`) `ScreenshotCache`（`set`/`get`/`clear` + Redis/内存），无三级 TTL 分层。

---

## 6. 前端截图流优化

### 6.1 优化策略

| 策略 | 说明 | 效果 |
|------|------|------|
| 帧率限制 | 最大 10fps | 减少带宽和 CPU |
| requestAnimationFrame | 对齐浏览器渲染帧 | 流畅渲染 |
| Canvas 渲染 | 使用 Canvas 而非 img 标签 | 更高效 |
| 差量更新 | 仅更新变化区域 | 减少绘制 |
| 懒渲染 | 不可见时停止渲染 | 节省资源 |
| WebCodecs | 使用硬件解码 | CPU 使用率降低 |

### 6.2 截图流管理器

```typescript
class ScreenshotStreamManager {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private maxFps: number = 10;
  private minInterval: number = 100;
  private lastRenderTime: number = 0;
  private pendingFrame: string | null = null;
  private isRendering: boolean = false;
  private isVisible: boolean = true;
  private rafId: number | null = null;

  constructor(canvas: HTMLCanvasElement, maxFps: number = 10) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d")!;
    this.maxFps = maxFps;
    this.minInterval = 1000 / maxFps;
    this.setupVisibilityObserver();
  }

  private setupVisibilityObserver(): void {
    document.addEventListener("visibilitychange", () => {
      this.isVisible = !document.hidden;
      if (!this.isVisible) {
        this.stopRendering();
      }
    });
  }

  onFrame(base64Data: string): void {
    if (!this.isVisible) return;
    this.pendingFrame = base64Data;
    this.scheduleRender();
  }

  private scheduleRender(): void {
    if (this.isRendering || this.rafId !== null) return;

    const now = performance.now();
    const elapsed = now - this.lastRenderTime;
    const delay = Math.max(0, this.minInterval - elapsed);

    this.rafId = window.setTimeout(() => {
      this.rafId = null;
      this.renderFrame();
    }, delay);
  }

  private renderFrame(): void {
    if (!this.pendingFrame || this.isRendering) return;

    this.isRendering = true;
    const img = new Image();

    img.onload = () => {
      if (this.canvas.width !== img.width || this.canvas.height !== img.height) {
        this.canvas.width = img.width;
        this.canvas.height = img.height;
      }
      this.ctx.drawImage(img, 0, 0);
      this.lastRenderTime = performance.now();
      this.pendingFrame = null;
      this.isRendering = false;

      if (this.pendingFrame) {
        this.scheduleRender();
      }
    };

    img.onerror = () => {
      this.isRendering = false;
    };

    img.src = `data:image/jpeg;base64,${this.pendingFrame}`;
  }

  private stopRendering(): void {
    if (this.rafId !== null) {
      clearTimeout(this.rafId);
      this.rafId = null;
    }
    this.pendingFrame = null;
  }

  destroy(): void {
    this.stopRendering();
  }
}
```

### 6.3 截图流 WebSocket 协议

```json
{
    "type": "screenshot.update",
    "device_id": "emulator-01",
    "data": "base64_encoded_jpeg",
    "timestamp": 1716000000.123,
    "width": 1280,
    "height": 720,
    "quality": 80,
    "frame_id": "abc123"
}
```

### 6.4 截图请求协议

```json
// Client → Server
{
    "type": "screenshot.subscribe",
    "device_id": "emulator-01",
    "fps": 5,
    "quality": 80
}

// Client → Server (取消订阅)
{
    "type": "screenshot.unsubscribe",
    "device_id": "emulator-01"
}

// Server → Client (单次截图请求)
{
    "type": "screenshot.request",
    "device_id": "emulator-01",
    "quality": 95
}
```

---

## 7. 性能指标

### 7.1 截图性能基准

| 指标 | 目标值 | 测量方法 |
|------|--------|---------|
| 截图延迟 (Windows) | < 5ms | DXGI 截图 |
| 截图延迟 (ADB) | < 50ms | nemu/scrcpy |
| SSIM 检测 | < 5ms | 4x 降采样 |
| JPEG 压缩 | < 10ms | 1280x720 @80 |
| 端到端延迟 | < 200ms | Agent → Client |
| 帧率 | 10fps | 稳定截图流 |
| 带宽 | < 500KB/s | 10fps @50KB/帧 |
