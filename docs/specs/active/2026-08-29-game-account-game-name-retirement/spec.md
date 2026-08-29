# spec: GameAccount.game_name 退役 — 游戏维度归一化到 GameProfile (window-centric 收尾)

> spec_id: 2026-08-29-game-account-game-name-retirement
> type: refactor | 规模: 大 (>500 行 diff, DB 迁移 ×2, API 契约变更) | 创建: 2026-08-29
> 三份核心文档章节: docs/architecture/features-overview.md §9.1 (系统设置—实为账户体系一章的 GameAccount)、docs/architecture/overview.md

## 问题（架构盘点结论）

TD-259 #23 引入 `GameAccount.game_profile` FK（注释约定"替代 game_name 字符串弱关联"），但**迁移只建了字段、没接通链路**：

| 事实 | 数据 |
|------|------|
| `GameAccount.game_profile` 关联率 | **0/4**（现有 4 条账户全部 NULL） |
| 唯一性约束 | 仍为 `(owner, game_name, username)` — 字符串承担"游戏维度"唯一性 |
| 写入路径 | serializer 只收 `game_name`；前端表单只提交 `game_name` |
| 批量导入 / 登录测试 / 统计聚合 | 全部读写 `game_name` 字符串 |
| `GameProfile.game_name` | 已 `unique=True` 全局主标识（无 owner，全局共享） |

**反模式**：FK 已建模却 dead 化；同一"游戏维度"存在两条表示（GameProfile 实体 vs GameAccount.game_name 字符串），约束/表单/展示三处错位。属架构未归一。

## 目标

制定并执行**四阶段**收敛：`game_profile` 成为 `GameAccount` 的唯一游戏维度，`game_name` 字符串字段在兼容过渡后从数据契约中退役删除。

## 方案

| 方案 | 描述 | 结论 |
|------|------|------|
| A | 完整收敛：写入/展示路径迁移到 profile → 数据回填 + 约束迁移 → drop 字符串字段 → 前端契约同步 | **选 A** |
| B | 仅接通 FK + 回填约束，保留 game_name 为冗余快照 | 拒绝（架构仍双字段） |
| C | 维持现状 | 拒绝（用户已否决） |

**兼容策略**：P1-P2 双轨兼容（仍接受 `game_name` 输入，后端 find_or_create profile 并绑定；展示统一改读 `profile.game_name`）；P3 用数据迁移回填后断开字符串写入并 drop 字段；旧客户端破坏面在 P3 一次性收口并随前端同步发布。

## 阶段状态表

| 阶段 | 内容 | diff 预估 | 状态 |
|------|------|----------|:---:|
| P1 | 后端写入/读取迁移（serializer find_or_create + 展示=profile + 视图过滤） | ~120 行 + 测试 | ✅ 已提交 ea663a9 |
| P2 | 数据回填迁移 + game_profile NOT NULL + unique_together 迁移 | ~40 行 + 迁移 | ✅ 已提交 a116d8e |
| P3 | 断开字符串写入、drop game_name 字段、前端表单/展示/契约同步 | ~200 行 | ✅ 已提交 187296a + 收尾 77c2e18/5f9d3bc |
| P4 | 验收：accounts 全量测试 + 账户 e2e + 全量回归 + game_name 引用残留清零 | — | ⏳ |
| P5 | **扩展(用户 2026-08-29 追加)**: GameStateRule.game_name → game_profile FK | ~120 行 + 迁移 | 🔧 后端完成, 待 commit (随 P6 同迁移 0010) |
| P6 | **扩展**: GameVersionCheck.game_name → game_profile FK（去冗余字符串） | ~40 行 + 迁移 | 🔧 后端完成, 待 commit (随 P5 同迁移 0010) |
| P7 | **扩展**: MarketplaceItem.game_name → game_profile FK + 前端去硬编码游戏选项 | ~150 行 + 前端 | 🔧 后端完成 (迁移 0057), **前端 Marketplace.tsx 改造未开始** |
| P8 | 验收(扩展)：gamestate/tasks 全量测试 + game_name 引用清零 + 归档 | — | ⏳ |

> 每阶段完成 → 更新本表状态 + completed-features；commit 粒度 = 每阶段 1 commit（§4.10 阶段拆分，单阶段 diff < 1500 行）。

## 已定决策（用户/调查确认）

1. **唯一游戏维度 = `GameProfile`**；`GameProfile.game_name` 为唯一显示名（全局唯一，无 owner）。
2. **数据迁移键** = `game_name`（全局）`GameProfile.objects.get_or_create(game_name=acc.game_name)`，与 owner 无关。
3. P2 后 `game_profile` 列 **NOT NULL、blank=False**；P3 移除 `unique_together(owner, game_name, username)` 的 game_name 项，改为 `(owner, game_profile, username)`。
4. P1 起展示层 `game_name` 输出 = `profile.game_name`（method field，profile 缺省时 fallback 旧值仅到 P2 前）。
5. ~~`GameProfile.game_name`（model 自带）与其它模型（Device、GameStatusRule、VersionCheck 等）的各自游戏名**不属于本 spec 范围**，不动。~~ **已废弃 (2026-08-29 用户否决)**: 从架构角度看，`GameStateRule` / `GameVersionCheck` / `MarketplaceItem` 各自持有独立 `game_name` 字符串 = 同一"游戏维度"的多套表示，属未归一化。全部纳入本 spec 扩展阶段 P5-P7 收敛到 game_profile FK。
6. 前端 `api.generated.ts` 在 P3 末通过 `npm run generate:api-types` 再生成（需按先重启 backend 再生成）。P7 后需再次生成以同步 GameStateRule/MarketplaceItem 契约。

### 扩展范围 P5-P7 映射明细（2026-08-29 用户追加调查）

| 模型 | 现状 | 收敛方案 |
|------|------|---------|
| `gamestate.GameStateRule.game_name` | CharField(255)，ViewSet 过滤 `?game_name=`，admin list_filter | 改为 `game_profile` FK（null=True 过渡）→ 数据回填 get_or_create → NOT NULL；serializer 输出 `game_profile` + 展示名；视图过滤改 `game_profile`；admin 同步 |
| `gamestate.GameVersionCheck.game_name` | CharField(100)，无 API（仅 admin+测试） | 同上收敛到 `game_profile` FK；admin/__str__ 同步 |
| `tasks.MarketplaceItem.game_name` | CharField(100, default='通用')，publish 接收字符串，前端 GAME_OPTION_KEYS 硬编码 | 改为 `game_profile` FK（null=True 表示"通用"）；publish API 接受 game_profile_id；前端选项改从 GameProfile 拉取（去硬编码）+ 展示用 profile 名 |

## 风险与限制

- P3 drop 字段对未升级的旧客户端/旧缓存响应为破坏性变更 → 与前端表单迁移同 commit 合并发布。
- 迁移回填需在 P2 前对生产数据做 dry-run 验证重复 game_name 与空值。
- `accounts_gameaccount` 表 `unique_together` 变更引索重建，迁移文件需在空窗执行（dev 小数据可忽略）。

## spec-context

B2 大修改 → 归档时必写 `docs/archive/spec-context/2026-08-29-game-account-game-name-retirement-context.md`（N151 盘点/方案评分/关键决策/用时）。