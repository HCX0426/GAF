---
date: 2026-07-30
topic: [template-match, transparent-png, alpha-mask, opencv, coordinate-system]
priority: high
cross_refs: [N191, N182, N183, N184]
status: active
created_by: AI
trigger: 用户测试 `resources/BrownDust-II/tasks/get_email.json` 第一个节点 `open_mailbox` 失败, 模板匹配置信度 0.1745 (阈值 0.8). 诊断发现 BD2 模板 PNG (邮箱.png) 是 RGBA 带 41.3% 透明像素, PIL.convert('RGB') 把透明区域填成纯黑 (0,0,0), cv2.matchTemplate 把纯黑透明像素当作"模板内容"匹配, 导致置信度从 0.97 跌到 0.17.
symptom: [template-match-low-confidence, transparent-png-alpha-loss, pil-convert-rgb-black-fill, opencv-matchtemplate-no-alpha-awareness, bd2-template-png-rgba]
solution: 加载模板时保留 alpha 通道作为 mask, 匹配时用 cv2.matchTemplate(..., mask=alpha) 让透明区域不贡献差异. cv2.matchTemplate 只有 TM_SQDIFF/TM_CCORR_NORMED 支持 mask, TM_CCOEFF_NORMED 不支持, 当 alpha_mask 存在且 cv_method 不支持 mask 时自动切到 TM_CCORR_NORMED.
diff_keywords: [transparent-png, alpha-mask, matchtemplate, confidence, rgba]
related_files:
  - worker/src/engine/nodes/template_match.py
  - worker/src/utils/coord_transformer.py
  - resources/BrownDust II/templates/get_email/邮箱.png
  - resources/BrownDust II/tasks/get_email.json
  - .ai-memory/lessons/N191-schema-unification-data-flow-checklist.md
  - .ai-memory/lessons/N182-bug-investigation-three-dimensional-root-cause.md
---

# N195: 透明 PNG 模板 alpha 通道丢失导致 matchTemplate 置信度异常偏低

## 现象

`get_email.json` 第一个节点 `open_mailbox` (template_match) 在 BD2 主界面执行失败:

```
confidence=0.1745, threshold=0.8 → fail
loc=(24,10), scale_ratio=0.8019, template=47x36→38x29
```

但同一张截图 + 同一个模板, 用诊断脚本 (cv2.imdecode + cv2.matchTemplate) 全图匹配置信度 **0.9314**, ROI 内匹配也能到 0.5795. 节点 ROI 内匹配 0.1745 异常偏低.

## 根因 (三维定位)

### 维度 1: 代码层 (具体 bug)

`TemplateMatchNode._load_template()` (worker/src/engine/nodes/template_match.py:551) 用 `PIL.Image.open(path).convert('RGB')` 加载模板, 然后 `cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)` 转 OpenCV BGR.

**问题**: BD2 模板 `邮箱.png` 是 **RGBA** 模式 (47x36, 41.3% 像素完全透明 alpha=0). `PIL.convert('RGB')` 会把透明区域填成纯黑 (0,0,0). 转成 BGR 后, 透明像素的 BGR 值 = (0,0,0).

`cv2.matchTemplate(search_region, template, TM_CCOEFF_NORMED)` 不知道哪些像素是透明的, 把纯黑透明像素当作"模板内容"去匹配. 实际截图里对应位置不是纯黑 (邮箱图标背景是游戏 UI), TM_CCOEFF_NORMED 算出来的归一化相关系数大幅偏低 → confidence=0.1745.

### 维度 2: 架构层 (为何没早发现)

- N191 schema 归一化解决的是字段/标签/坐标系一致性问题 (roi 数组被正确读取, roi_coord_type 被正确传递), 但**不覆盖节点内部匹配算法正确性**
- 模板加载层 (`_load_template`) 是节点内部实现, schema 归一化扫描覆盖不到
- 透明 PNG 模板在测试数据里没出现过 — 单测用纯色 JPEG 模板, 集成测试用 mock, 真实 BD2 资源 (RGBA PNG) 是首次端到端测试才暴露

### 维度 3: 流程层 (为何反复犯)

- BD2-AUTO 原版用 PIL 加载模板 + matchTemplate, 但 BD2-AUTO 的模板可能是 JPEG 或已 flatten 的 PNG (无 alpha)
- GAF porting 时直接搬了 BD2-AUTO 的加载逻辑, 没考虑资源文件格式差异
- 没有对模板资源做"是否带 alpha 通道"的扫描, 也没有对模板加载路径做单元测试覆盖 RGBA case

## 验证 (复现 + 修复确认)

### 复现脚本关键输出

```
PIL original mode: RGBA, size: (47, 36)
[A] PIL→BGR black pixels: 699/1692 (41.3%)
[B] cv2.imdecode black pixels: 699/1692 (41.3%)
[C] cv2.IMREAD_UNCHANGED alpha: transparent (alpha=0) pixels: 699/1692 (41.3%)
[A] vs [B] absdiff mean: 0.00, max: 0  # PIL 和 cv2 加载结果完全一致

# 同一张截图 + 同一个模板, 不同匹配方式:
[node _load_template path, TM_CCOEFF_NORMED no mask]  confidence=0.1745, loc=(23,10)
[cv2.imdecode path,        TM_CCOEFF_NORMED no mask]  confidence=0.1745, loc=(23,10)
[with alpha mask,          TM_CCORR_NORMED       ]    confidence=0.9703, loc=(0,0)
```

关键结论:
1. 模板加载方式 (PIL vs cv2.imdecode) **无关**, 因为两者都丢 alpha 通道填黑
2. 加 alpha mask 后 confidence 从 0.1745 → 0.9703, 证明根因就是透明像素被当模板内容

### 修复后节点直接调用确认

```
=== Running TemplateMatchNode.execute() ===
Result:
  success     = True
  confidence  = 0.9703
  match_loc   = {'x': 1255, 'y': 22}
  clicked     = True
```

## 修复方案

### 1. `_load_template_with_alpha()` (新方法)

拆分原 `_load_template` 为:
- `_load_template_with_alpha() -> (template_bgr, alpha_mask)`: 保留 alpha 通道作为 mask
- `_load_template() -> template_bgr`: backward-compat wrapper, 内部调 `_load_template_with_alpha()` 丢 mask

alpha_mask 提取逻辑:
```python
if pil_img.mode in ('RGBA', 'LA') or \
   (pil_img.mode == 'P' and 'transparency' in pil_img.info):
    pil_rgba = pil_img.convert('RGBA')
    pil_rgb = pil_rgba.convert('RGB')
    alpha_mask = np.array(pil_rgba)[:, :, 3]  # 单通道 uint8 mask
else:
    pil_rgb = pil_img.convert('RGB')
    alpha_mask = None
```

### 2. `_match_with_scaling()` (transformer 路径)

- 加载模板时取 alpha_mask
- 缩放模板时同步缩放 alpha_mask (用 `cv2.INTER_NEAREST` 保证二值化, 避免 mask 边缘出现 0~255 过渡值)
- 匹配前检查 `cv_method` 是否支持 mask:
  - 支持: `cv2.TM_SQDIFF`, `cv2.TM_SQDIFF_NORMED`, `cv2.TM_CCORR`, `cv2.TM_CCORR_NORMED`
  - 不支持: `cv2.TM_CCOEFF`, `cv2.TM_CCOEFF_NORMED`, `cv2.TM_SQDIFF_NORMED` (OpenCV 文档说支持但实测有问题)
- 当 alpha_mask 存在且 cv_method 不支持 mask 时, 自动切到 `TM_CCORR_NORMED` 并 log warning

### 3. Legacy 路径 (无 transformer)

同样应用 alpha mask 逻辑 (line 1138+).

### 4. 日志增强

匹配完成 log 增加 `alpha_mask=yes/no` 和 method 切换标注:
```
匹配完成(scaled): method=TM_CCOEFF_NORMED→TM_CCORR_NORMED(透明PNG),
  confidence=0.9703, threshold=0.80, loc=(15, 9), scale_ratio=0.8019,
  template=47x36→38x29, alpha_mask=yes
```

## 失败模式 (禁止)

- ❌ `PIL.Image.open(path).convert('RGB')` 加载带透明背景的 PNG 模板 → ✅ 用 `_load_template_with_alpha` 保留 alpha 作为 mask
- ❌ `cv2.matchTemplate(TM_CCOEFF_NORMED, mask=alpha)` (该方法不支持 mask) → ✅ 自动切到 `TM_CCORR_NORMED`
- ❌ 缩放 alpha_mask 用 `INTER_LANCZOS4` (产生 0~255 过渡值) → ✅ 用 `INTER_NEAREST` 保持二值化
- ❌ 加载模板后不检查是否有 alpha 通道, 直接 matchTemplate → ✅ 检查 `alpha_mask is not None` 决定是否走 mask 路径
- ❌ 只修 `_match_with_scaling` 不修 legacy 路径 → ✅ 两条路径都修

## 诊断手法 (可复用)

### 手法 1: 全图 vs ROI 内匹配对比

```python
# A. 节点方法 (ROI 内 + scale)
res_a = cv2.matchTemplate(search_region, tpl_scaled, cv2.TM_CCOEFF_NORMED)
# B. 无 scale 直接 ROI 内
res_b = cv2.matchTemplate(search_region, tpl, cv2.TM_CCOEFF_NORMED)
# C. 全图 + scale (最宽容)
res_c = cv2.matchTemplate(img, tpl_scaled, cv2.TM_CCOEFF_NORMED)
```

如果 C 远高于 A/B, 说明 ROI 裁剪或 scale 有问题; 如果 A/B/C 都低, 说明模板本身有问题 (如透明 alpha).

### 手法 2: 透明通道检测

```python
tpl_unchanged = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
if tpl_unchanged.shape[2] == 4:
    alpha = tpl_unchanged[:,:,3]
    transparent_ratio = np.sum(alpha == 0) / alpha.size
    if transparent_ratio > 0.05:  # >5% 透明像素
        logger.warning("模板 %s 含 %.1f%% 透明像素, 必须用 alpha mask 匹配",
                       path, 100*transparent_ratio)
```

### 手法 3: mask 匹配对比

```python
# 无 mask
res_nomask = cv2.matchTemplate(search, tpl, cv2.TM_CCOEFF_NORMED)
# 有 mask (TM_CCORR_NORMED 支持 mask)
res_mask = cv2.matchTemplate(search, tpl, cv2.TM_CCORR_NORMED, mask=alpha)
# 如果 res_mask >> res_nomask, 根因是透明像素被当模板内容
```

## 检查清单 (修复后必跑)

```text
□ 1. 模板资源扫描: 用 cv2.IMREAD_UNCHANGED 加载所有 resources/*/templates/*.png,
     列出所有 shape[2]==4 且 transparent_ratio > 5% 的模板
□ 2. 单元测试: 新增 test_template_match_alpha_mask.py, 覆盖:
     - RGBA 模板 + alpha mask 匹配
     - RGB 模板 (无 alpha) 兼容性
     - method 自动切换 (TM_CCOEFF_NORMED → TM_CCORR_NORMED)
□ 3. 端到端: get_email.json open_mailbox 节点 confidence >= 0.9 (实测 0.9703)
□ 4. 回归: 其他 pipeline 的 template_match 节点不变 (无 alpha 模板走原路径)
□ 5. 日志: grep "alpha_mask=yes" 确认透明 PNG 模板走了 mask 路径
```

## 跨设备/跨场景适用性

- **Windows + BD2 (RGBA 模板)**: 必须用 alpha mask, 否则 confidence 0.17 vs 0.97
- **ADB + BD2 (同一套模板)**: 同样必须用 alpha mask (模板格式不变)
- **JPEG 模板 (无 alpha)**: 走原路径, alpha_mask=None, 无影响
- **PseudoBackground 截图模板**: 若截图保存为 PNG 带 alpha, 同样适用

## 与 N191/N184 关系

- **N191**: schema 归一化覆盖"字段/标签/坐标系一致", **不覆盖**节点内部算法正确性. 本 bug 是 N191 扫描盲区.
- **N184**: 节点可观测性硬约束. 本 bug 修复前 log 不记 alpha_mask 字段, AI 无法从日志反推"是不是透明 PNG 问题". 修复后 log 含 `alpha_mask=yes/no`, 满足 N184 可观测性.
- **N182**: 三维根因分析. 本 bug 用三维定位:
  - 维度 1 (代码): `_load_template` 丢 alpha
  - 维度 2 (架构): N191 扫描不覆盖节点内部算法
  - 维度 3 (流程): 资源文件格式未扫描, 单测未覆盖 RGBA case

## L0 硬约束升级建议 (待评估)

考虑升级到 `env-hardrules.md` L0 级:

```text
## 模板资源硬约束 (N195 衍生, 待评估)

- 所有 `resources/*/templates/*.png` 模板必须扫描是否带 alpha 通道
- 带 alpha 通道的模板 (transparent_ratio > 5%) 必须走 mask 匹配路径
- 新增模板资源时, CI 检查模板格式并标注是否带 alpha
```

当前不升级 L0, 理由: 本 bug 是一次性修复 (代码已改完), 不像 conda 环境/PowerShell heredoc 那样会反复触发. 留作 lesson 级别即可.
