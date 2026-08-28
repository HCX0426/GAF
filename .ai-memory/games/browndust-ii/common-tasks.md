---
maintainer: manual
source: GAF resources/BrownDust II 实际代码库 (2026-07-31 校验)
load_when:
- 新功能 (BD2 任务)
- BD2 pipeline 编写/调试
- BD2 任务模板参考
priority: medium
symptom:
- kb:game:bd2:common-tasks
- 日常任务
- BD2 pipeline
- 任务模板
solution: 12 个 BD2 pipeline 速查 + 模板路径约定 + 公共子流程; 完整参考见 bd2-task-reference.md
related_files:
- .ai-memory/games/browndust-ii/overview.md
- .ai-memory/games/browndust-ii/assets.md
- .ai-memory/games/browndust-ii/coordinate-system.md
- resources/BrownDust II/docs/task-reference.md
- resources/BrownDust II/manifest.json
- agent/src/engine/resource_resolver.py
created_by: AI
generated: 2026-06-16
last_manual_edit: 2026-07-31
---
# BD2 常见任务 (Common Tasks) - 速查索引

> **适用场景**: AI 写 BD2 pipeline 时快速查阅
> **⚠️ 权威参考**: 完整模板目录 + 管道流程 + 坐标转换 + 导航图 → **`resources/BrownDust II/docs/task-reference.md`**（新对话必读此文件）
> **资源根目录**: `resources/BrownDust II/`

## 1. 12 个 Pipeline 速查

> **格式**: JSON, `nodes` 数组, 位置: `resources/BrownDust II/tasks/*.json`

| # | 文件 | 描述 | 成熟度 | 备注 |
|:-:|------|------|:------:|------|
| 1 | login.json | 登录: 点开始游戏 → 关弹窗 → 回主菜单 | 🔧 待验证 | R37-P2 C2 PoC 覆盖 |
| 2 | sweep_daily.json | 日常扫荡 (饭团+火炬本) | 🔧 待验证 | — |
| 3 | daily_missions.json | 每日任务 | 🔧 待验证 | — |
| 4 | get_email.json | 收邮箱（含空邮箱分支 + back_to_main 子流程） | 🔧 已验证 | 2026-07-31: 空邮箱路径 + 返回主界面已修复 |
| 5 | get_guild.json | 收公会 | 🔧 待验证 | — |
| 6 | get_pvp.json | 收竞技场 | 🔧 待验证 | — |
| 7 | get_restaurant.json | 收餐厅 | 🔧 待验证 | — |
| 8 | intensive_decomposition.json | 装备精炼分解 | 🔧 待验证 | — |
| 9 | lucky_draw.json | 抽卡 | 🔧 待验证 | — |
| 10 | map_collection.json | 材料/金币吸收 | 🔧 待验证 | — |
| 11 | pass_activity.json | 活动关卡扫荡 | 🔧 待验证 | TD-013 已修 |
| 12 | pass_rewards.json | 通行证奖励 | 🔧 待验证 | — |

## 2. 公共子流程

| 文件 | 用途 | 被引用 |
|------|------|--------|
| `tasks/back_to_main.json` | 从任意子界面返回主界面（优先返回键模板 → ESC 降级） | get_email |
| `tasks/dismiss_popup.json` | 关闭通用弹窗（点击返回键 → 固定等待 2s） | — |

**待抽取候选**:
- `claim_all_rewards.json` — 全部领取 → 关闭结算

## 3. 模板路径约定

> **模板用中文名**, 路径解析由 `agent/src/engine/resource_resolver.py` 处理

| 类别 | 路径 |
|------|------|
| 公共 | `BrownDust II/templates/public/` |
| 登录 | `BrownDust II/templates/login/` |
| 扫荡 | `BrownDust II/templates/sweep_daily/` |
| 邮箱 | `BrownDust II/templates/get_email/` |
| 公会 | `BrownDust II/templates/get_guild/` |
| 竞技场 | `BrownDust II/templates/get_pvp/` |
| 餐厅 | `BrownDust II/templates/get_restaurant/` |
| 装备分解 | `BrownDust II/templates/intensive_decomposition/` |
| 抽卡 | `BrownDust II/templates/lucky_draw/` |
| 材料吸收 | `BrownDust II/templates/map_collection/` |
| 活动 | `BrownDust II/templates/pass_activity/` |
| 通行证 | `BrownDust II/templates/pass_rewards/` |

## 4. 节点类型速查

| type | 用途 | 关键 config 字段 |
|------|------|-----------------|
| `template_match` | 模板匹配（可点击） | `template`, `threshold`, `roi`, `click_on_match` |
| `ocr` | 文字识别（可点击） | `text`, `roi`, `click_on_match` |
| `wait` | 等待界面出现 | `mode` (template/fixed), `template`, `timeout` |
| `key_press` | 按键 | `key` (如 "esc") |
| `branch` | 条件分支 | `condition_variable`, `true_node_id`, `false_node_id` |
| `sub_pipeline` | 子流程引用 | `pipeline_path` |
| `direct_hit` | 直接点击坐标 | `x`, `y` |
| `long_press` | 长按 | `x`, `y`, `duration_ms` |

## 5. 关键文件

| 文件 | 用途 |
|------|------|
| `docs/task-reference.md` | **权威参考**（模板目录/管道流程/坐标转换/导航图/常见问题） |
| `tasks/*.json` | 13 个 pipeline（含 back_to_main 公共子流程） |
| `templates/*/` | 67 个模板图片，按功能分组 |
| `manifest.json` | 资源包清单 |
| `agent/src/engine/resource_resolver.py` | 模板路径解析 |
| `agent/src/utils/coord_transformer.py` | 坐标转换器 |
