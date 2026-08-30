# BrownDust II 故障排查指南

> **版本**: 1.0.0  
> **创建日期**: 2026-08-09  
> **适用**: 任务失败后的快速排查参考  
> **关联文档**: [task-reference.md](./task-reference.md), [roi-template-mapping.md](./roi-template-mapping.md)

---

## 1. 快速排查流程

```
任务失败报告
    │
    ├─ 1. 确认失败节点
    │   └─ 读取错误信息中的 node_id / error_type
    │
    ├─ 2. 检查上一节点状态
    │   └─ 上一节点成功? → 弹窗遮挡检测 (§2)
    │   └─ 上一节点失败? → 级联错误, 需先修上一节点
    │
    ├─ 3. 弹窗遮挡检测 (高频原因!)
    │   └─ 截取屏幕 → 用弹窗模板匹配
    │   └─ 检测到弹窗? → 执行 dismiss 流程
    │
    ├─ 4. 验证输入
    │   └─ 截图对比: 当前画面 vs 预期画面
    │   └─ 分辨率检查: 实际 vs 基准 (1920x1080)
    │
    ├─ 5. 验证配置
    │   └─ ROI 覆盖检查
    │   └─ 截图方法检查 (PrintWindow 优先)
    │   └─ 超时值检查 (OCR >= 15s)
    │
    └─ 6. 输出诊断结论
        └─ 配置问题 / 数据流问题 / 弹窗遮挡 / 代码问题
```

---

## 2. 高频故障场景

### 2.1 弹窗遮挡（★ 最常见）

**症状**: 上一节点成功，当前节点 OCR 全乱码或模板匹配失败

**弹窗特征**: 中间弹窗框 + 右上角 × 关闭按钮

**排查步骤**:
```bash
# Step 1: 截取当前屏幕，检查弹窗 (重点检查屏幕中央区域)
conda run -n gaf python worker/debug/_diag_popup.py \
    --popup-templates "templates/public/关闭按钮.png,templates/public/跳过.png" \
    --roi "[600, 200, 720, 680]"  # 屏幕中央区域

# Step 2: 如检测到弹窗，执行 dismiss
# - 在 pipeline 中添加 dismiss_popup 节点
# - 或手动点击右上角 × 关闭按钮
```

**常见弹窗类型**:
| 弹窗 | 位置 | 关闭方式 |
|------|------|----------|
| 活动公告 | 屏幕中央 | 点击右上角 × 或「关闭」按钮 |
| 签到弹窗 | 屏幕中央偏上 | 点击右上角 × 或「领取」按钮 |
| 系统提示 | 屏幕中央 | 点击右上角 × 或「确定」按钮 |
| 广告弹窗 | 屏幕中央偏下 | 点击右上角 × 或「跳过」按钮 |

**弹窗检测要点**:
1. 弹窗通常在屏幕中央，不在边缘
2. 关闭按钮 (×) 通常在弹窗右上角
3. 弹窗会遮挡下方所有内容，导致 OCR/模板匹配失败
4. 检测到弹窗后，必须先关闭弹窗再继续诊断

### 2.2 OCR 超时

**症状**: `wait_*` 节点 OCR 15s 超时，识别不到目标文本

**排查步骤**:
```bash
# Step 1: 全图 OCR 看目标文本在哪里
conda run -n gaf python worker/debug/_diag_ocr.py \
    --text "普通邮箱" \
    --compare-full

# Step 2: 对比全图 vs ROI 裁剪结果
# - 全图找到但 ROI 内找不到 → ROI 配置有误
# - 全图也找不到 → 文本可能不在当前画面

# Step 3: 如果 ROI 需要调整
# - 参考 task-reference.md 中各任务的 ROI 坐标
# - 建议在原基础上增加 ±10px 的 buffer
```

**常见原因**:
- ROI 裁剪掉了目标文本（y 值偏低或偏高）
- 界面未切换到目标页面（需要添加 wait_for_visible 验证）
- 弹窗遮挡了目标区域

### 2.3 模板匹配失败

**症状**: `template_match` 节点找不到目标模板

**排查步骤**:
```bash
# Step 1: 对比不同截图方法
conda run -n gaf python worker/debug/_diag_template.py \
    --template "templates/get_email/邮箱.png" \
    --roi "[1564,28,95,61]"

# Step 2: 同 ROI 降级匹配
conda run -n gaf python worker/debug/_diag_template_fallback.py \
    --primary-template "templates/get_email/邮箱.png" \
    --roi "[1564,28,95,61]" \
    --mapping "resources/BrownDust II/docs/roi-template-mapping.md"
```

**截图方法选择（BD2）**:
| 方法 | 置信度 | 适用场景 |
|------|--------|----------|
| **PrintWindow** | 0.94+ | **推荐**，BD2 窗口渲染 |
| GDI | 0.17 | 可能包含窗口边框，置信度低 |
| DXGI | — | 全屏截图，可能黑屏 |
| WGC | — | 需要 Win10 1903+ |

### 2.4 点击后界面无变化

**症状**: `click_on_match` 成功，但游戏界面没有切换

**排查步骤**:
1. 截取屏幕确认界面状态
2. 检查是否有弹窗拦截了点击（执行弹窗检测）
3. 验证点击坐标是否正确（参考 roi-template-mapping.md）
4. 如有需要，添加 `wait_for_visible` 验证节点

---

## 3. 各任务常见问题

### 3.1 get_email（领取邮箱）

| 步骤 | 节点 | 常见问题 | 排查脚本 |
|------|------|----------|----------|
| 1 | click_email | 邮箱图标找不到 | `_diag_template.py --template "邮箱.png"` |
| 2 | wait_regular_email | OCR 超时（弹窗遮挡） | `_diag_popup.py` → `_diag_ocr.py` |
| 3 | detect_empty_email | 空邮箱标识识别失败 | `_diag_template.py --template "空邮箱标识.png"` |
| 4 | click_claim_all | 「全部领取」按钮找不到 | `_diag_ocr.py --text "全部领取"` |
| 5 | back_to_main | 子流程 coord_transformer 缺失 | 检查 sub_pipeline 配置 |

**关键界面转换**: 主界面 → 邮箱列表 → （空/非空分支）→ 主界面

### 3.2 get_guild（公会）

| 步骤 | 节点 | 常见问题 | 排查脚本 |
|------|------|----------|----------|
| 1 | click_guild | 公会图标找不到 | `_diag_template.py --template "公会标识.png"` |
| 2 | wait_guild_shop | 公会商店不可见 | `_diag_template.py --template "公会商店.png"` |
| 3 | back_to_main | 返回主界面失败 | `_diag_popup.py` → 弹窗检测 |

### 3.3 sweep_daily（每日扫荡）

| 步骤 | 节点 | 常见问题 | 排查脚本 |
|------|------|----------|----------|
| 1 | click_sweep | 扫荡按钮找不到 | `_diag_template.py --template "扫荡标识.png"` |
| 2 | select_stage | 关卡选择失败 | `_diag_template.py --template "第七关.png"` |
| 3 | wait_production | 产出界面超时 | 增加 timeout 到 30s+ |

### 3.4 daily_missions（每日/每周任务）

| 步骤 | 节点 | 常见问题 | 排查脚本 |
|------|------|----------|----------|
| 1 | click_task | 任务面板打开失败 | `_diag_ocr.py --text "任务"` |
| 2 | wait_daily | 每日任务加载慢 | 增加 timeout 到 20s+ |
| 3 | claim_all | 「全部获得」按钮找不到 | `_diag_ocr.py --text "全部获得"` |

---

## 4. 快速诊断命令速查

```bash
# 1. 完整诊断 (推荐)
conda run -n gaf python worker/debug/_diag_full.py \
    --pipeline get_email --node wait_regular_email

# 2. 节点隔离测试
conda run -n gaf python worker/debug/_diag_node.py \
    --node-id wait_regular_email \
    --pipeline resources/BrownDust\ II/tasks/get_email.json

# 3. OCR 验证
conda run -n gaf python worker/debug/_diag_ocr.py \
    --text "普通邮箱" --roi "[214,10,333,276]" --compare-full

# 4. 模板匹配验证
conda run -n gaf python worker/debug/_diag_template.py \
    --template "templates/get_email/邮箱.png" --roi "[1564,28,95,61]"

# 5. 弹窗检测
conda run -n gaf python worker/debug/_diag_popup.py \
    --popup-templates "templates/public/返回键1.png,templates/public/跳过.png"

# 6. 同 ROI 降级匹配
conda run -n gaf python worker/debug/_diag_template_fallback.py \
    --primary-template "templates/get_email/邮箱.png" \
    --roi "[1564,28,95,61]" \
    --mapping "resources/BrownDust II/docs/roi-template-mapping.md"
```

---

## 5. 关键参数速查

### 5.1 BD2 已知参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 基准分辨率 | 1920×1080 | 所有 ROI 基于此设计 |
| 实际窗口 | ~1540×866 | 物理像素，DPI 缩放 ~150% |
| 推荐截图方法 | PrintWindow | 置信度 0.94+ |
| OCR 首次初始化 | ~3.4s | timeout 建议 >= 15s |
| 公共子流程 | `back_to_main.json` | 返回键 → ESC 降级 |

### 5.2 ROI 坐标转换

```python
# 基准坐标 → 实际坐标
screen_h, screen_w = screen.shape[:2]
scale_x = screen_w / 1920
scale_y = screen_h / 1080

actual_x = int(base_x * scale_x)
actual_y = int(base_y * scale_y)
actual_w = int(base_w * scale_x)
actual_h = int(base_h * scale_y)
```

### 5.3 阈值建议

| 场景 | 阈值 | 说明 |
|------|------|------|
| 模板匹配（精确） | 0.85+ | 关键节点，必须高置信度 |
| 模板匹配（宽松） | 0.70 | 弹窗检测等辅助匹配 |
| OCR 置信度 | 0.50+ | 文本识别本身不确定性大 |
| 截图方法切换 | 0.90 | 若某方法置信度 < 0.9，尝试其他方法 |

---

## 6. 调试日志规范

### 6.1 日志格式

```
[DIAG] Level=<1/2/3> | Pipeline=<name> | Node=<id> | Error=<type>
[DIAG] Step=<n>/<total> | Action=<action> | Result=<result>
[DIAG] Finding=<description>
[DIAG] Recommendation=<suggestion>
```

### 6.2 日志示例

```
[DIAG] Level=1 | Pipeline=get_email | Node=wait_regular_email | Error=NODE_TIMEOUT
[DIAG] Step=1/7 | Action=确认失败节点 | Result=node_id=wait_regular_email, type=wait(ocr)
[DIAG] Step=2/7 | Action=检查上一节点 | Result=open_mailbox: ✅ success (confidence=0.9364)
[DIAG] Step=3/7 | Action=弹窗遮挡检测 | Result=⚠️ 检测到弹窗! 匹配到 [返回键1.png]
[DIAG] Step=4/7 | Action=重新验证输入 | Result=弹窗关闭后界面正确显示
[DIAG] Finding=open_mailbox 点击后出现意外弹窗，遮挡了目标区域
[DIAG] Recommendation=在 open_mailbox 后添加 dismiss_popup 节点
```

### 6.3 日志目录

```
debug/YYYYMMDD/diag_<method>/
  ├── screenshots/
  │   ├── annotated/    # 标注后的截图
  │   └── raw/          # 原始截图
  ├── logs/
  │   └── diag_<timestamp>.log
  └── result.json       # 诊断结果
```

---

## 7. 预防措施

### 7.1 Pipeline 设计规范

- [ ] 每个 `click_on_match` 后必须有 `wait_for_visible` 验证
- [ ] 返回主界面必须复用 `back_to_main.json` 子流程
- [ ] 关键节点配置 `continue_on_error: true`
- [ ] OCR timeout 设置为 >= 15s（包含引擎初始化时间）
- [ ] 弹窗检测优先：上一节点成功但当前失败时先查弹窗

### 7.2 资源文件检查

- [ ] 确保 `docs/task-reference.md` 存在且更新
- [ ] 确保 `docs/roi-template-mapping.md` 存在且更新
- [ ] 模板图像清晰、无压缩失真
- [ ] ROI 坐标覆盖目标区域（有 ±10px buffer）

---

## 8. 升级诊断

如果 Level 1-2 诊断无法定位问题，升级到 Level 3（设计级诊断）：

```bash
# Level 3: 设计级诊断
conda run -n gaf python worker/debug/_diag_full.py \
    --pipeline get_email --node wait_regular_email --level 3
```

Level 3 会检查：
- 界面切换验证节点是否完整
- 公共子流程是否正确复用
- 错误处理是否完善
- 硬编码坐标值问题
- 节点命名规范性

---

## 附录: 文档索引

| 文档 | 路径 | 用途 |
|------|------|------|
| 任务参考文档 | `docs/task-reference.md` | 界面导航图、任务入口/出口 |
| ROI-模板映射 | `docs/roi-template-mapping.md` | 同 ROI 多模板降级匹配 |
| Pipeline 定义 | `tasks/*.json` | 节点配置、边连接 |
| ROI 配置 | `config/rois.json` | ROI 区域坐标 |
| 模板图像 | `templates/**/*.png` | 模板匹配用 |
| Manifest | `manifest.json` | 任务清单、版本信息 |