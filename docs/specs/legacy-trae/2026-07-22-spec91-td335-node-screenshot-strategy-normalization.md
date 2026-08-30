---
spec_id: spec-91
title: TD-335 — agent 识别节点截图获取策略归一化 (长期, 文档化 + OCR 错误信息清理)
created: 2026-07-22
status: ✅ done
commit: -
related_td: [TD-335]
related_n: [N167, N151, N182, N183]
depends_on: [spec-88]
blocks: []
priority: P2
size: 小 (文档更新 + OCR 错误信息清理, ~80 行)
---

# spec-91: TD-335 — agent 识别节点截图获取策略归一化 (长期)

## 背景与问题

### 根因分析

TD-335 短期 fix (OCR `_get_image` device fallback) 已在本轮交付 (commit 在 spec-88 之前), 6 tests in `TestOCRNodeGetImageFallback` 全通过。长期归一化方向 A (推荐): 所有识别节点统一走模式 A (自给自足 + context override), 控制流/动作节点保持各自模式。

现状 (spec-88 TD-336 已加 §2.8 节点契约表):
- **5 识别节点 (模式 A, 自给自足)**: `template_match` / `feature_match` / `color_detect` / `maa_actions` / `ocr` (短期 fix 后) — 全部 `device.capture_screen()` + context override
- **1 控制流节点 (模式 B, 截图喂子节点)**: `wait` — 截图后 `context.set_variable("image", image)` 喂给子 OCR 节点
- **3 动作节点 (模式 D, debug 截图)**: `click` / `key_press` / `swipe` — 截图仅用于 debug 存档

**问题**: §2.8 节点契约表 OCR 行仍写 "修复后加 device fallback" / "修复后半 self-sufficient" (修复前措辞), 短期 fix 已交付后应更新为现状描述。OCR execute() L91 错误信息 'No image available in context for OCR' 不准确 (现在有 device fallback, 应为 'context empty + device capture failed')。

### N167 7 维度评分

| 维度 | 分 | 说明 |
|------|---|------|
| 1. 架构长远性 | 3 | 文档化节点契约, 长期价值中等 (规范沉淀) |
| 2. 全局归一化 | 4 | 统一 5 识别节点截图策略描述, 分类 9 节点 |
| 3. 改动量 | 5 | 文档为主 + 1 处错误信息清理, < 80 行 |
| 4. 测试覆盖 | 4 | OCR 已有 6 tests (TestOCRNodeGetImageFallback), 不需新增 |
| 5. 文档完整 | 5 | §2.8 节点契约表 + §7 测试规范已存在, 仅更新现状描述 |
| 6. 风险 | 5 | 文档改动 + 1 处错误信息, 极低风险 |
| 7. 长期维护 | 4 | 规范沉淀, 长期受益 |
| **合计** | **30** | ≥ 5 分阈值, AI 自决 (循环模式) |

## 方案 A (推荐): 文档现状化 + OCR 错误信息清理

### 改动清单

1. **`docs/general/design/pipeline-authoring-guide.md` §2.8 节点契约表**:
   - OCR 行: "context 依赖 (修复后加 device fallback)" → "自给自足 (context 优先 + device fallback)"
   - OCR 行 能力边界: "requires-upstream (修复后半 self-sufficient)" → "self-sufficient"
   - 契约说明: 移除 "修复后" / "修复方向" 措辞, 改为现状描述

2. **`worker/src/engine/nodes/ocr.py`**:
   - L86 注释: "Step 2: Acquire image from context" → "Step 2: Acquire image (context override → device fallback)"
   - L91 错误信息: 'No image available in context for OCR' → 'No image available (context empty + device capture failed/unavailable)'
   - L443-445 docstring: 移除 "Without it, the OCR node fails with..." (短期 fix 已交付, 现状描述)

3. **`docs/general/tech-debt/active.md`**: TD-335 段落迁出
4. **`docs/general/tech-debt/fixed.md`**: TD-335 ✅ FIXED 段落追加
5. **`docs/general/tech-debt/README.md`**: sync_tech_debt_counts 自动同步

### 验收标准

- §2.8 节点契约表 OCR 行更新为现状描述 (无 "修复后" 措辞)
- OCR L91 错误信息更准确 (含 device fallback 失败描述)
- 全套 agent tests GREEN (OCR 6 tests 仍通过)
- TD-335 迁移到 fixed.md
- pre-commit hook 全过

### 验收标准调整说明 (N167 维度 4)

原 TD-335 验收标准 "9 个节点截图策略归一化到单一模式 (A 或 B)" 不准确 — 9 个节点不全是识别节点, 不应全部归一化到同一模式。实际应改为 "5 个识别节点截图策略归一化到模式 A (已完成, 短期 fix 后 OCR 也符合), 1 控制流节点保持模式 B, 3 动作节点保持模式 D, 文档化分类"。

## 循环模式说明

本 spec 为循环模式第 4 spec (接 spec-88/89/90 后), N167 评分 30 分 AI 自决, 改动量小 (< 80 行) 选为循环过渡 spec。
