---
spec_id: spec-93
title: TD-330 sub-spec 1 — ExecutionMonitorPanel inline style + hex color 治理
created: 2026-07-22
status: ✅ done
commit: '-'
related_td: [TD-330]
related_n: [N167, N151]
depends_on: []
blocks: []
priority: P2
size: 中 (1 文件 ~59 处治理 + CSS class 抽取, ~150 行 diff)
---

# spec-93: TD-330 sub-spec 1 — ExecutionMonitorPanel inline style + hex color 治理

## 背景与问题

### 根因分析

TD-330 (frontend 全仓 inline style + hex color + aria-label 治理, P2 长期) 登记 2026-07-21, 验收标准: inline style < 100 / hex color < 50. 当前 pages/ 总量: inline 570 (超标 5.7x) + hex 232 (超标 4.6x). TD-330 计划按 page 拆分 5-10 个 sub-spec, 每 spec 治理 1-3 page.

本 spec 为 TD-330 第 1 sub-spec, 治理 `frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx` (排名 #1, inline 31 + hex 28 = 59). 该文件含 3 类样式:

1. **暗色终端子主题** (C 类保留): 日志终端区域用 VS Code 风格暗色 (#1e1e1e bg / #252526 toolbar / #333 border / #3c3c3c input / #555 border / #ccc/#ddd/#d4d4d4 text / #888/#666/#bbb secondary) — 业务调色板, 不映射 antd token (antd 是浅色主题), 抽取为 CSS class
2. **浅色主题 hex** (A 类迁移): #d9d9d9 border / #fafafa bg / #e8e8e8 border / #fff bg / #52c41a success / #1890ff primary / #fa8c16 warning / #ff4d4f error / #999 text-secondary / #333 text — 映射 antd design token
3. **语义色常量** (C 类保留): LOG_COLORS map (#d4d4d4/#e6db74/#f44747) + annotation colors (#52c41a/#ff4d4f) — 内容驱动, 保留为常量

### N167 7 维度评分

| 维度 | 分 | 说明 |
|------|---|------|
| 1. 架构长远性 | 3 | TD-330 首批 sub-spec, 建立治理模式 (终端子主题 CSS class + antd token 迁移), 后续 sub-spec 复用 |
| 2. 全局归一化 | 4 | 复用 TD-294 utility class 体系 + 新增 .gaf-terminal* CSS class, 不引入新模式 |
| 3. 改动量 | 3 | 1 文件 ~59 处 + components.css ~30 行新增, ~150 行 diff |
| 4. 测试覆盖 | 3 | 前端无单元测试, 靠 typecheck (tsc --noEmit) + lint + 视觉验证 |
| 5. 文档完整 | 4 | 本 spec + TD-330 已有详细方案 + components.css 注释 |
| 6. 风险 | 3 | UI 视觉改动 (暗色终端抽取为 class, 浅色 hex 改 token), 有 design token 体系保底 |
| 7. 长期维护 | 4 | 每治理一批, 长期受益; 终端子主题 class 可复用于其他日志面板 |
| **合计** | **24** | ≥ 5 分阈值, AI 自决 (循环模式) |

## 方案 A (推荐): 暗色终端 CSS class 抽取 + 浅色 hex → antd token + 布局 utility class

### 改动清单

1. **`frontend/src/styles/components.css`** 新增 `.gaf-terminal*` class 系列:
   - `.gaf-terminal` (容器: bg #1e1e1e + flex-col)
   - `.gaf-terminal-toolbar` (bg #252526 + border-bottom #333)
   - `.gaf-terminal-input` (bg #3c3c3c + border #555 + color #ddd)
   - `.gaf-terminal-log` (padding 6px 10px + font Consolas + line-height 20px + color #d4d4d4)
   - `.gaf-terminal-log-entry` (white-space pre-wrap + word-break break-all)
   - `.gaf-terminal-log-empty` (color #666 + padding 40px 0)
   - `.gaf-terminal-log-time` (color #888, mr-sm)
   - `.gaf-terminal-log-level` (mr-sm + font-weight 600 for ERROR)
   - 各 class 配 `body.theme-dark` 覆盖 (暗色主题下终端保持暗色, 不随主题翻转)

2. **`frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx`** 治理:
   - **A 类 (antd token)**: import `theme` from antd, `const { token } = theme.useToken()`, 替换:
     - `#d9d9d9` → `token.colorBorder`
     - `#fafafa` → `token.colorBgLayout`
     - `#e8e8e8` → `token.colorBorderSecondary`
     - `#fff` → `token.colorBgContainer`
     - `#52c41a` (button) → `token.colorSuccess`
     - `#1890ff` (button) → `token.colorPrimary`
     - `#fa8c16` (button) → `token.colorWarning`
     - `#ff4d4f` (perf metric) → `token.colorError`
     - `#999` → `token.colorTextSecondary`
     - `#333` → `token.colorText`
   - **B 类 (utility class)**: 转换布局 inline style:
     - `height: '100%'` → `gaf-h-full`
     - `fontSize: 13` → `gaf-text-13`
     - `whiteSpace: 'pre-wrap'` → `gaf-whitespace-pre-wrap`
     - `position: 'relative'` → `gaf-position-relative`
     - `overflow: 'hidden'` → `gaf-overflow-hidden`
   - **C 类 (保留)**: LOG_COLORS + annotation colors 保留为常量 (语义色, 内容驱动); 暗色终端 hex 移到 CSS class
   - **aria-label**: icon-only Button (screenshot 按钮) 检查 aria-label 覆盖

3. **`docs/general/tech-debt/active.md`**: TD-330 段落更新 (inline 570→539, hex 232→204, 治理 31+28=59 处)
4. **`docs/general/tech-debt/fixed.md`**: 不追加 (TD-330 整体未闭环, sub-spec 进度记在 active.md TD-330 段)

### 验收标准

- ExecutionMonitorPanel.tsx inline style 数 31 → ≤ 15 (C 类暗色终端 + 语义色常量保留)
- ExecutionMonitorPanel.tsx hex color 数 28 → ≤ 10 (C 类 LOG_COLORS + annotation 保留)
- `npx tsc --noEmit` 0 errors
- `npm run lint` 0 errors
- components.css 新增 .gaf-terminal* class 含 body.theme-dark 覆盖

### 循环模式说明

本 spec 为循环模式第 6 spec (接 spec-92 后), N167 评分 24 分 AI 自决. TD-330 第 1 sub-spec, 建立治理模式供后续 sub-spec 复用.
