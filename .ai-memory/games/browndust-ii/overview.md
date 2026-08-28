---
maintainer: manual
source: BD2 官方文档 + 玩家社区共识
load_when:
- 新功能 (BD2 任务)
- 调试 BD2 任务
- BD2 游戏相关
priority: medium
symptom:
- kb:game:bd2:overview
- browndust-ii
- BD2
- 游戏档案
solution: BD2 概述 (类型/平台/UI) + 4 大模式 (剧情/竞技/日常) + GAF 适配点
related_files:
- .ai-memory/games/browndust-ii/coordinate-system.md
- .ai-memory/games/browndust-ii/assets.md
- .ai-memory/games/browndust-ii/common-tasks.md
- frontend/src/pages/Setup/StepRecommendedTemplates.tsx
- backend/tasks/models.py
created_by: AI
generated: 2026-06-16
last_manual_edit: 2026-07-11
---
# BrownDust II (棕色尘埃 2) - 游戏概述

> **适用场景**: AI 写 BD2 任务前必读, 了解游戏背景
> **维护者**: manual (游戏内容需人类确认, AI 仅整理)
> **GAF 状态**: 🔧 12 pipelines 已从 BD2-AUTO 移植到 `resources/BrownDust II/tasks/` (11 ready for e2e, 1 pending — pass_activity needs TD-013)

## 1. 游戏基本信息

| 项目 | 内容 |
|------|------|
| **全名** | BrownDust II / 棕色尘埃 2 / 브라운더스트 2 |
| **开发商** | NEOWIZ (韩国) |
| **平台** | iOS / Android (手游) |
| **类型** | SRPG (策略角色扮演) |
| **首发** | 2022-06 全球发行 |
| **语言** | 韩文 / 英文 / 日文 / 中文 (繁/简) |
| **付费模式** | F2P + Gacha |
| **核心玩法** | 9 人小队回合制战斗 + 角色收集 + 剧情 |

## 2. 4 大游戏模式

### 2.1 📖 剧情模式 (Story)

- **类型**: 主线 + 支线 + 角色个人剧情
- **节奏**: 单关 5-10 分钟, 9 人回合制
- **GAF 适配**: ✅ 已支持 (Pipeline 节点覆盖)
- **典型操作**: 选关 → 选角色 → 拖拽站位 → 自动战斗 → 结算

### 2.2 ⚔️ 竞技场 (Arena/PVP)

- **类型**: 实时 PVP, 跨服对战
- **节奏**: 单局 2-3 分钟, 实时操作
- **GAF 适配**: ⚠️ 部分支持 (需手动操作, 自动化风险高)
- **典型操作**: 编队 → 匹配 → 选 Ban → 战斗

### 2.3 🎯 日常副本 (Daily Dungeon)

- **类型**: 金币/经验/材料 副本
- **节奏**: 单次 1-2 分钟, 每天 3-5 次
- **GAF 适配**: ✅ 强适配 (重复模式, 模板化)
- **典型操作**: 选副本 → 编队 → 自动战斗 → 领取奖励

### 2.4 🏰 攻城战 (Guild War)

- **类型**: 公会集体战
- **节奏**: 每周 1 次, 每场 30 分钟
- **GAF 适配**: ❌ 不支持 (需实时协调, 风险高)
- **典型操作**: 公会成员配合作战

## 3. UI 元素速查 (GAF 视角)

| 元素 | 坐标特征 | 截图识别 |
|------|----------|----------|
| **主菜单** | 屏幕底部 5 个 Tab | OCR "战斗/角色/剧情/商城/菜单" |
| **战斗场景** | 上方 9 人 + 下方敌人 | 模板匹配 "敌方" 血条 |
| **角色选择** | 网格 6x4 | OCR 角色名 |
| **背包** | 滚动列表 | OCR 物品名 |
| **抽卡 (Gacha)** | 中心动画 + 周围 UI | 模板匹配抽卡按钮 |
| **聊天** | 右下角浮窗 | OCR 文本 |
| **广告弹窗** | 中央遮罩 + 关闭 X | 模板匹配 "X" 按钮 |

## 4. GAF 适配现状

| 功能 | 状态 | 说明 |
|------|:----:|------|
| 模拟器控制 (LDPlayer/BlueStacks) | ✅ | 主流模拟器已适配 |
| 截图识别 (WGC/DXGI) | ✅ | 1280x720 / 1920x1080 主流分辨率 |
| OCR 识别 (PaddleOCR/RapidOCR) | ✅ | 中/英/日/韩 4 语言 |
| 模板匹配 (OpenCV) | ✅ | 需玩家提供模板图 |
| 触控操作 (PostMessage/SendInput) | ✅ | 模拟器透传 |
| 战斗逻辑 (回合制) | ✅ | Pipeline 节点覆盖 |
| 抽卡识别 | 🔧 | 模板 + OCR, 准确率 90% |
| 实时 PVP | ❌ | 风险高, 暂不支持 |
| 反作弊规避 | ⚠️ | 部分绕过, 需人工监控 |

## 5. 已知问题 (3 个)

### 5.1 频繁更新导致 UI 变化 (N46)

**问题**: BD2 每月大版本, UI 布局可能变
**影响**: 模板/OCR 配置失效, 任务失败
**解决**: 社区维护 BD2 模板库, GAF 加载时检查版本

### 5.2 服务器分区 (N47)

**问题**: 亚服/韩服/全球服 UI 略不同
**影响**: 同一模板不通用
**解决**: 模板库按 server 分组, 启动时选择

### 5.3 抽卡动画时间不固定 (N48)

**问题**: 抽卡动画 3-10 秒不等
**影响**: 截图时机不对, 误识别
**解决**: 动画结束后再识别, 用 `wait` 节点 (`mode: "template"`, 匹配模板后继续)

## 6. 推荐任务模板 (GAF 视角)

| 任务 | 难度 | 模板成熟度 | 风险 |
|------|:----:|:----------:|:----:|
| 日常副本 (金币/经验) | ⭐ | 🔧 待验证 | 低 |
| 主线剧情 | ⭐⭐ | 🔧 待验证 | 中 |
| 角色升级 (吃经验书) | ⭐ | 🔧 待验证 | 低 |
| 抽卡 (单抽/十连) | ⭐⭐ | 🔧 待验证 | 中 |
| 竞技场 | ⭐⭐⭐ | 🔧 待验证 | 高 |
| 公会战 | ⭐⭐⭐⭐ | 🔧 待验证 | 高 |

## 7. 相关文件

- `frontend/src/pages/Setup/StepRecommendedTemplates.tsx` - BD2 推荐模板导入
- `backend/tasks/models.py` - 任务模型 (含 BD2 模板字段)
- `resources/BrownDust II/tasks/` - 实际 BD2 pipelines (12 JSON, 移植自 BD2-AUTO)
- `resources/BrownDust II/manifest.json` - 资源包清单 (12 pipelines, 67 PNG templates)
- `agent/examples/daily_sign_in.yaml` - legacy YAML 示例 (实际 pipeline 为 JSON)
- `agent/examples/stage_battle.yaml` - legacy YAML 示例 (实际 pipeline 为 JSON)

## 8. 反思 (Reflection)

- **BD2 是 GAF 主要目标游戏**: 玩家社区贡献模板
- **UI 变化是最大风险**: 月版本更新需重新适配
- **PVP 不建议自动化**: 反作弊 + 道德风险
- **日常副本最适合**: 重复模式, 模板化, 风险低
- **相关**: coordinate-system.md / assets.md / common-tasks.md
