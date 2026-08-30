---
maintainer: manual
source: GAF resources/BrownDust II 实际代码库 (2026-07-11 校验)
load_when:
- 新功能 (BD2 任务)
- BD2 模板制作
- 资源库更新
- 模板路径解析
priority: medium
symptom:
- kb:game:bd2:assets
- 资源模板
- template-library
- resource-pack
solution: resources/BrownDust II/ 真实结构 (config/pipelines/templates/manifest) + 67 PNG 中文模板 + resource_resolver 路径解析
related_files:
- .ai-memory/games/browndust-ii/overview.md
- .ai-memory/games/browndust-ii/common-tasks.md
- resources/BrownDust II/manifest.json
- resources/BrownDust II/config/settings.json
- resources/BrownDust II/config/rois.json
- worker/src/engine/resource_resolver.py
- backend/resources/models.py
- frontend/src/pages/Setup/StepRecommendedTemplates.tsx
created_by: AI
generated: 2026-06-16
last_manual_edit: 2026-07-11
---
# BD2 资源 (Assets) - GAF 速查

> **适用场景**: AI 制作 BD2 模板, 资源导入, 模板路径解析
> **资源根目录**: `resources/BrownDust II/` (NOT `assets/templates/browndust-ii/`)
> **诚实状态**: 67 PNG 模板已入库, 全部 🔧 待 e2e 验证 (未对真实游戏验证)

## 1. 资源目录结构 (实际代码库)

```
resources/BrownDust II/
├── manifest.json              # 版本 1.1.0, 11 ready + 1 pending
├── config/
│   ├── settings.json          # base_resolution / ocr_engine / screenshot_method
│   └── rois.json              # ROI 定义
├── custom_tasks/
│   └── template.json          # 自定义任务模板
├── monitors/
│   ├── popup_handler.yaml     # 弹窗处理监控
│   └── story_skip.yaml        # 跳过剧情监控
├── pipelines/                 # 12 个 JSON pipeline (执行用)
│   ├── login.json
│   ├── sweep_daily.json
│   ├── daily_missions.json
│   ├── get_email.json
│   ├── get_guild.json
│   ├── get_pvp.json
│   ├── get_restaurant.json
│   ├── intensive_decomposition.json
│   ├── lucky_draw.json
│   ├── map_collection.json
│   ├── pass_activity.json     # ❌ TD-013 pending
│   └── pass_rewards.json
├── tasks/                     # 旧格式 YAML 示例 (非执行用)
│   ├── daily_sign_in.yaml     # 状态机格式
│   └── stage_battle.yaml      # chain + 状态机混合
└── templates/                 # 67 PNG 模板 (中文命名)
    ├── common/                # (仅 .gitkeep)
    ├── public/                # 9 PNG: 主界面/地图标识/返回键1/返回键2/自动战斗开关/跳过/每日收集/游戏卡带/闪避标识
    ├── login/                 # 1 PNG: 开始游戏
    ├── sweep_daily/           # 13 PNG: 第九关/快速狩猎按钮/狩猎按钮/天赋本/材料本/经验本/金币本/...
    ├── get_pvp/               # 9 PNG: 竞技场标识/进入竞技场/自动战斗/pvp地图/...
    ├── get_guild/             # 3 PNG: 公会标识/公会标识2/公会商店
    ├── get_restaurant/        # 5 PNG: 进入餐厅/餐馆标识/下一阶段/升级/结算X
    ├── get_email/             # 2 PNG: 邮箱/空邮箱标识
    ├── intensive_decomposition/  # 12 PNG: 分解按钮/精炼/装备标识/筛选标识/跳过/确认/制作/...
    ├── lucky_draw/            # 1 PNG: 抽完标识
    ├── map_collection/        # 7 PNG: 材料吸收/金币吸收/探寻/吸收材料完成/...
    ├── pass_activity/         # 4 PNG: 战斗/无法快速战斗/第10关/第15关
    └── pass_rewards/          # 1 PNG: 通行证标识
```

> **模板总数**: 67 PNG (manifest.json 确认), 按 per-task 子目录组织
> **命名**: 中文 (如 `主界面.png`), NOT 英文 (`btn_start.png` 等英文名不存在)

## 2. manifest.json (实际格式)

**文件**: `resources/BrownDust II/manifest.json`

```json
{
  "name": "BrownDust II",
  "version": "1.1.0",
  "target_app": "BrownDust II",
  "author": "BD2-AUTO port to GAF (Phase R29/R37-P2)",
  "gaf_version": ">=1.0.0",
  "description": "BrownDust II Resource Pack - ported from BD2-AUTO/src/auto_tasks/Default. Contains 12 pipelines + 67 PNG templates. Status: 11 pipelines ready for e2e (...), 1 pipeline pending pipeline-schema extensions for if-elif fallback (TD-013: pass_activity). OCR verify migration bugs fixed in R37-P2 (5 wait nodes corrected from template to ocr mode)."
}
```

> **注意**: 旧文档中的 `meta.json` (角色/装备/UI 三分类 + version/server/themes 字段) **不存在**, 是虚构内容。

## 3. config/settings.json (实际格式)

**文件**: `resources/BrownDust II/config/settings.json`

```json
{
  "base_resolution": [1280, 720],
  "ocr_engine": "rapidocr",
  "screenshot_method_preference": "printwindow",
  "input_method_preference": "auto",
  "screenshot_cache_ttl": 50,
  "humanize_enabled": true,
  "humanize_offset": 5
}
```

**关键字段**:
| 字段 | 值 | 说明 |
|------|-----|------|
| `base_resolution` | `[1280, 720]` | 窗口分辨率 (运行时实际分辨率) |
| `ocr_engine` | `"rapidocr"` | OCR 引擎 |
| `screenshot_method_preference` | `"printwindow"` | 截图方式首选 |
| `input_method_preference` | `"auto"` | 输入方式自动选择 |
| `humanize_enabled` | `true` | 拟人化点击 |

> **注意**: pipeline 内的 `metadata.original_base_res: [1920, 1080]` 是 ROI 坐标基准分辨率, 与 settings 的 `base_resolution: [1280, 720]` 不同 — 运行时自动缩放。

## 4. 模板路径解析 (resource_resolver.py)

**文件**: `worker/src/engine/resource_resolver.py`
**函数**: `resolve_resource_path(path_str) -> Optional[Path]`

### 4.1 解析顺序

1. **绝对路径** → 直接使用 (如存在)
2. **GAF_RESOURCE_ROOT 环境变量** → `$GAF_RESOURCE_ROOT/<path>`
3. **CWD/resources/** → `<CWD>/resources/<path>`
4. **CWD/../resources/** → `<CWD>/../resources/<path>` (agent 从 GAF/agent/ 运行, resources 在 GAF/resources/)
5. **从 engine/ 向上查找** → walk up from `worker/src/engine/` 找 `resources` 兄弟目录
6. **直接匹配** → `<root>/<path>` (如 `BrownDust II/templates/public/主界面.png`)
7. **短路径补全** → `<root>/<game>/templates/<path>` (如 `public/主界面` → `BrownDust II/templates/public/主界面`)
8. **扩展名补全** → 无扩展名时尝试 `.png`/`.jpg`/`.jpeg`/`.bmp`/`.webp`

### 4.2 短路径支持

BD2-AUTO pipeline 作者使用短路径 (如 `public/主界面`), resolver 自动补全 `BrownDust II/templates/` 前缀, 搜索所有 `<root>/<game>/templates/` 子目录。

```python
# worker/src/engine/resource_resolver.py
# Example: resolve_resource_path("BrownDust II/templates/public/主界面.png")
# → <GAF>/resources/BrownDust II/templates/public/主界面.png

# Short form also works: resolve_resource_path("public/主界面")
# → searches <root>/BrownDust II/templates/public/主界面.png
```

## 5. 模板子目录与命名 (实际)

> **命名规范**: 中文语义命名 (如 `开始游戏.png`), NOT 英文 `btn_start.png`
> **组织**: 按 per-task 子目录, 公共模板放 `public/`

| 子目录 | PNG 数 | 关键模板 |
|--------|:------:|---------|
| `public/` | 9 | `主界面.png`, `地图标识.png`, `返回键1.png`, `返回键2.png`, `自动战斗开关.png`, `跳过.png`, `每日收集.png`, `游戏卡带.png`, `闪避标识.png` |
| `login/` | 1 | `开始游戏.png` |
| `sweep_daily/` | 13 | `第九关.png`, `第七关.png`, `快速狩猎按钮.png`, `狩猎按钮.png`, `天赋本.png`, `材料本.png`, `经验本.png`, `金币本.png`, `扫荡标识.png`, ... |
| `get_pvp/` | 9 | `竞技场标识.png`, `进入竞技场.png`, `自动战斗.png`, `pvp地图.png`, `pvp地图2.png`, `倍数.png`, `离开.png`, `选项完成.png`, `X.png` |
| `get_guild/` | 3 | `公会标识.png`, `公会标识2.png`, `公会商店.png` |
| `get_restaurant/` | 5 | `进入餐厅.png`, `餐馆标识.png`, `下一阶段.png`, `升级.png`, `结算X.png` |
| `get_email/` | 2 | `邮箱.png`, `空邮箱标识.png` |
| `intensive_decomposition/` | 12 | `分解按钮.png`, `精炼.png`, `装备标识.png`, `筛选标识.png`, `跳过.png`, `确认.png`, `制作.png`, `18加.png`, `加十.png`, `R.png`, `SR.png`, `UR.png` |
| `lucky_draw/` | 1 | `抽完标识.png` |
| `map_collection/` | 7 | `材料吸收.png`, `金币吸收.png`, `探寻.png`, `吸收材料完成.png`, `金币吸收完成.png`, `第七章1.png`, `第七章2.png` |
| `pass_activity/` | 4 | `战斗.png`, `无法快速战斗.png`, `第10关.png`, `第15关.png` |
| `pass_rewards/` | 1 | `通行证标识.png` |
| `common/` | 0 | (仅 `.gitkeep`) |
| **合计** | **67** | |

## 6. 后端资源模型 (backend/resources/)

**文件**: `backend/resources/models.py`

| 模型 | 行号 | 用途 |
|------|:----:|------|
| `ResourcePack` | 5 | 资源包 (对应 `resources/BrownDust II/`) |
| `Template` | 105 | 模板记录 |
| `TemplateAnnotation` | 205 | 模板标注 |
| `RecognizerBenchmark` | 242 | 识别器基准测试 |
| `TemplateEffectiveness` | 277 | 模板有效性跟踪 |

**任务执行关联**: `backend/agents/views.py:1989` — `resource_pack_id` 参数, 执行任务时指定资源包。

## 7. 前端导入入口

**文件**: `frontend/src/pages/Setup/StepRecommendedTemplates.tsx`
**作用**: Setup 向导 step 4, 提供 "BD2-AUTO 导入" 选项
**后端 API**: `backend/accounts/views.py` `ImportBd2View` (class 定义), URL: `/api/v2/accounts/init/import-bd2/`

> **注意**: 旧文档引用的 `frontend/src/pages/Setup/Bd2ImportPanel.tsx` **不存在**, 实际文件是 `StepRecommendedTemplates.tsx`。

## 8. 已知问题

### 8.1 pass_activity TD-013 (待修复)

**问题**: `pass_activity.json` 需 if-elif fallback, 当前为 skeleton only
**状态**: ❌ pending (manifest.json 明确标注)
**修复方向**: pipeline-schema 扩展支持 if-elif (TD-013)

### 8.2 全部 pipeline 待 e2e 验证

**问题**: 11 个 pipeline 移植完成但未对真实 BD2 游戏验证
**状态**: 🔧 待验证
**验证范围**: R37-P2 C2 PoC 仅覆盖 login, 其余 10 个未验证

### 8.3 handle_hunt_result 简化 (Phase B)

**问题**: `sweep_daily.json` 的 handle_hunt_result 简化为单次 click_back, 原 BD2-AUTO 逻辑含 cancel fallback
**状态**: 🔧 Phase B 待补全

## 9. 相关文件

- `resources/BrownDust II/manifest.json` - 资源包清单 (v1.1.0)
- `resources/BrownDust II/config/settings.json` - 运行时配置
- `resources/BrownDust II/config/rois.json` - ROI 定义
- `resources/BrownDust II/templates/` - 67 PNG 模板 (13 子目录)
- `worker/src/engine/resource_resolver.py` - 路径解析器
- `backend/resources/models.py` - ResourcePack/Template 等模型
- `backend/agents/views.py` - resource_pack_id 参数 (line 1989)
- `frontend/src/pages/Setup/StepRecommendedTemplates.tsx` - BD2 导入 UI

## 10. 反思 (Reflection)

- **资源库是 GAF 飞轮的"内容侧"**: 67 PNG 模板 + 12 pipeline 移植自 BD2-AUTO
- **诚实状态**: 全部 🔧 待验证, 无任何 pipeline 标 ✅ (未对真实游戏验证)
- **中文模板命名**: 与 BD2-AUTO 源一致, 非 GAF 自创英文名
- **resource_resolver 支持短路径**: 兼容 BD2-AUTO pipeline 约定 (省略 game/templates 前缀)
- **旧文档虚构内容已清除**: meta.json 三分类 / pipeline_nodes.py 代码示例 / Bd2ImportPanel.tsx 均不存在
- **相关**: overview.md / coordinate-system.md / common-tasks.md
