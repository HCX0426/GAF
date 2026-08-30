---
maintainer: manual
source: BD2 玩家社区共识 + GAF 实践
load_when:
- 新功能 (BD2 任务)
- 调试 BD2 坐标
- BD2 模板制作
priority: medium
symptom:
- kb:game:bd2:coordinates
- coordinate-system
- 坐标系
- 分辨率
solution: 4 主流分辨率 + 3 坐标变换 (绝对/相对/缩放) + 5 易错点
related_files:
- .ai-memory/games/browndust-ii/overview.md
- .ai-memory/games/browndust-ii/common-tasks.md
- worker/src/engine/resource_resolver.py
- frontend/src/components/Common/DpiScaler.tsx
- resources/BrownDust II/config/rois.json
- resources/BrownDust II/config/settings.json
created_by: AI
generated: 2026-06-16
last_manual_edit: 2026-07-11
---
# BD2 坐标系 (Coordinate System) - GAF 速查

> **适用场景**: AI 写 BD2 任务时坐标定位, 模板匹配, OCR 区域
> **核心问题**: 不同模拟器/分辨率下坐标不通用, 需要 DPI 缩放

## 1. 4 大主流分辨率

| 分辨率 | 长宽比 | 模拟器 | GAF 推荐度 |
|--------|--------|--------|:----------:|
| **1280x720** | 16:9 | LDPlayer 默认 | ⭐⭐⭐⭐⭐ |
| **1920x1080** | 16:9 | BlueStacks 5 | ⭐⭐⭐⭐ |
| **2560x1440** | 16:9 | 4K 显示器 | ⭐⭐⭐ |
| **2400x1080** | 20:9 | 全面屏模拟器 | ⭐⭐ |

**Pipeline ROI 基准**: 1920x1080 (`metadata.original_base_res` in pipeline JSONs — ROIs defined at this resolution)
**窗口/截图分辨率**: 1280x720 (`settings.json base_resolution` — actual window/screenshot size, engine scales ROIs from 1920x1080 base to this)

## 2. 3 种坐标系统

### 2.1 绝对坐标 (Absolute)

**定义**: 屏幕像素坐标, 从 (0, 0) 到 (width, height)
**例子**: `click(x=640, y=360)` - 屏幕中心
**适用**: 单机任务, 固定分辨率
**缺点**: 分辨率变化时失效

### 2.2 相对坐标 (Relative)

**定义**: 相对于参考点的偏移, 范围 [0.0, 1.0]
**例子**: `click(rel_x=0.5, rel_y=0.5)` - 屏幕中心 50%/50%
**适用**: 跨分辨率任务
**转换**: `abs_x = rel_x * screen_width`

### 2.3 缩放坐标 (Scaled)

**定义**: 相对模板分辨率的缩放比例
**例子**: 模板 1280x720, 实际 1920x1080, 缩放 = 1.5x
**公式**: `abs_x = template_x * (actual_w / template_w)`

## 3. DPI 缩放 (Windows 特有)

### 3.1 Windows DPI 问题

**症状**: Windows 10/11 高 DPI 缩放 (125%/150%/200%) 导致坐标偏移
**后果**: 模拟器内坐标与系统坐标不一致
**解决**: 🔧 待验证 — 原 `worker/src/devices/windows/benchmark.py` 未在代码库中找到, 实际 DPI 检测路径待确认

### 3.2 GAF 的 DPI 处理

```python
# coordinate utility (已删除)
def scale_coordinate(x: int, y: int, source_dpi: int, target_dpi: int) -> tuple:
    """缩放坐标到目标 DPI"""
    scale = target_dpi / source_dpi
    return int(x * scale), int(y * scale)
```

### 3.3 前端 DPI 处理

```typescript
// frontend/src/components/Common/DpiScaler.tsx
export const DpiScaler = ({ children, scale = 1.0 }) => {
  return <div style={{ transform: `scale(${scale})` }}>{children}</div>
}
```

## 4. 5 个 AI 易错点

### 4.1 ❌ 假设固定坐标 (N49)

**错误**: `click(x=640, y=360)` 硬编码
**后果**: 分辨率变化时点击错位
**正确**: 用相对坐标 `click(rel_x=0.5, rel_y=0.5)` 或缩放

### 4.2 ❌ 忽略状态栏高度 (N50)

**错误**: 状态栏高度 24px 算入点击区
**后果**: 实际点击比预期高 24px
**正确**: `effective_y = click_y - status_bar_height` (Android = 24px, iOS = 20px)

### 4.3 ❌ 模拟器窗口 vs 全屏 (N51)

**错误**: 用全屏分辨率算坐标
**后果**: 模拟器窗口模式下点击错位
**正确**: 用 `device.window_size`, 不用 `screen_size`

### 4.4 ❌ 旋转屏幕 (N52)

**错误**: 假设横屏, 实际竖屏
**后果**: 坐标完全错乱
**正确**: `device.orientation` 检查, 竖屏时坐标 x/y 交换

### 4.5 ❌ 多显示器 (N53)

**错误**: 假设主显示器 (0, 0)
**后果**: 副显示器上坐标偏移
**正确**: 用 `device.position` 获取窗口实际位置

## 5. BD2 UI 关键 ROI (1920x1080 基准, [x, y, w, h])

> **来源**: `resources/BrownDust II/config/rois.json` (verified)
> **格式**: `[x, y, w, h]` — ROIs defined at `original_base_res` (1920x1080), engine scales to actual window resolution
> **Pipeline 引用**: `roi_coord_type: "base"` in node config

| 元素 | ROI [x, y, w, h] | rois.json key | 备注 |
|------|------------------|---------------|------|
| **主菜单标识** | [1720, 20, 120, 70] | public.main_menu | 主界面识别 |
| **返回键** | [120, 20, 100, 66] | public.back_button | 通用返回 |
| **地图标识** | [1740, 20, 175, 88] | public.map_indicator | 地图界面识别 |
| **取消按钮** | [850, 600, 60, 40] | public.cancel_button | 弹窗取消 |
| **确认对话框** | [655, 344, 600, 700] | public.confirm_dialog | 通用确认 |
| **背包入口** | [330, 1000, 57, 43] | public.backpack | 主界面背包 |
| **PVP 确认按钮** | [795, 906, 399, 137] | public.confirm_button_pvp | PVP 确认 |
| **结算文字** | [806, 429, 313, 137] | public.end_game_text | 战斗结算 |
| **返回文字** | [811, 935, 327, 95] | public.back_image_text | 返回提示 |
| **图鉴文字** | [209, 19, 307, 69] | public.game_collection_text | 图鉴入口 |
| **闪避指示** | [1600, 833, 170, 140] | public.dodge_indicator | 战斗闪避 |

## 6. 模板制作 SOP (5 步)

```
[Step 1] 截图当前 UI (1280x720)
    │
[Step 2] 用 GIMP/Photoshop 裁剪关键元素 (50x50 ~ 200x200)
    │
[Step 3] 保存到 resources/BrownDust II/templates/<category>/ (e.g. public/, login/)
    │
[Step 4] 在 Pipeline JSON 中引用: {"type": "template_match", "config": {"template": "BrownDust II/templates/public/主界面.png", "threshold": 0.8, "roi": [1720,20,120,70], "roi_coord_type": "base", "click_on_match": true}}
    │
[Step 5] 验证: 跨 3 个分辨率测试, 准确率 ≥ 95%
```

## 7. 速查表

| 场景 | 推荐坐标类型 | 理由 |
|------|--------------|------|
| 单一模拟器, 固定分辨率 | 绝对 | 简单直接 |
| 跨模拟器, 同分辨率 | 相对 | 分辨率统一 |
| 跨模拟器, 跨分辨率 | 缩放 | 兼容性最好 |
| Windows 高 DPI | DPI 缩放 | 必须 |
| 多显示器 | 窗口相对 | 显示器独立 |
| 旋转屏幕 | 检测后交换 | 避免 hard-code |

## 8. 反思 (Reflection)

- **坐标系是 GAF 跨平台核心**: 同一 Pipeline 跨 Win/macOS/Linux 必须坐标转换
- **DPI 是 Windows 最大坑**: macOS/Linux 一般无 DPI 问题
- **BD2 模板社区共建**: 玩家贡献, GAF 加载时按 server 选择
- **5 易错点都是"假设"**: 假设分辨率/状态栏/横屏/单显示器 → 必须运行时检测
- **相关**: overview.md / assets.md / common-tasks.md
