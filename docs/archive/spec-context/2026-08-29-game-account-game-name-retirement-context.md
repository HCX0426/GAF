---
summary: spec 2026-08-29-game-account-game-name-retirement 执行上下文（决策/N151 评估/N167 评分/用时）
applies_to: [backend, frontend]
spec: 2026-08-29-game-account-game-name-retirement
last_updated: 2026-08-29
---

# spec-context: GameAccount / 扩展模型 game_name → game_profile 收敛

## 决策摘要（用户 2026-08-29）

- 原始 spec 仅覆盖 `GameAccount.game_name`（P1-P4）。用户审查后端时发现 `GameStateRule` / `GameVersionCheck` / `MarketplaceItem` 各自持独立 `game_name` 字符串 = 同一"游戏维度"多套表示，属未归一化，否决"仅不动"提议，要求全部纳入收敛（P5-P7）。
- 收敛策略（选 A）：写入/展示迁移到 `game_profile` FK → 数据回填（同名 get_or_create）→ drop 字符串字段 → 前端契约同步。
- P3 一次性收口旧客户端破坏面，与前端同步发布。

## N151 架构盘点（扩展阶段）

| 模型 | 旧表示 | 新表示 | 迁移 |
|------|--------|--------|------|
| `accounts.GameAccount.game_name` | CharField | `game_profile` FK (NOT NULL) | P1-P3 (ea663a9/a116d8e/187296a) |
| `gamestate.GameStateRule.game_name` | CharField(100, default='通用') | `game_profile` FK (null=True=通用) | P5 (b67b34c, 迁移 0010) |
| `gamestate.GameVersionCheck.game_name` | CharField | `game_profile` FK | P6 (b67b34c, 迁移 0010) |
| `tasks.MarketplaceItem.game_name` | CharField(100, default='通用') | `game_profile` FK (null=True=通用) | P7 (b67b34c, 前端 f4fbbea) |

- 展示层统一从 `game_profile.game_name` 读取；`game_name` 仅作为兼容输入解析（batch import `get_or_create`）与 `game_name_display` 输出字段保留。
- 后端 publish API 接受 `game_profile_id`；serializer 输出 `game_profile_detail` + `game_name`（profile 名为空时回退 '通用'）。

## N167 七维度评分（扩展阶段 P5-P7，总分 32/35）

1. 架构长远性 — 5：消除游戏维度多套表示，单一权威源 `game_profile`
2. 全局归一化 — 5：与 P1-P3 同构，全栈一致
3. 数据完整性 — 5：FK + 回填迁移，无孤儿
4. 向后兼容 — 4：P1-P3 已留兼容输入；P5-P7 扩展模型无外部旧客户端，破坏面小
5. 实现成本 — 4：3 模型同构迁移，复用 P3 模式
6. 测试覆盖 — 5：336 passed（accounts/gamestate/tasks）
7. 长期维护成本 — 4：字符串字段清零，后续无双写维护

## 关键决策

- D1: 扩展模型 `game_profile` 允许 null（'通用'语义），与 P3 GameAccount NOT NULL 区分（账户必须归属游戏，规则/市场项可通用）。
- D2: 前端 Marketplace.tsx 去硬编码 `GAME_OPTION_KEYS`，改 `fetchGameProfiles` 动态拉取；publish 发 `game_profile` id；展示直接用后端 `game_name`（已含 '通用'）。
- D3: 不重新生成 `api.generated.ts` 全量（需 backend 运行）；仅本地 `TaskMarketplaceItem` 接口补 `game_profile?` 字段，保持类型安全。

## 用时

- P5-P7 后端（b67b34c）：含调查 + 3 模型迁移 + serializer + 前端，约 40 min。
- P7 前端（f4fbbea）：Marketplace.tsx 改造 + skills.ts 接口 + tsc 校验，约 15 min。
- 验收 P4/P8：pytest 336 passed / 80s。

## 验证证据

- `pytest backend/accounts backend/gamestate backend/tasks` → 336 passed。
- 前端 `npx tsc --noEmit` → 0 errors。
- grep `backend` `game_name`：仅 `GameProfile.game_name` / `game_profile__game_name` / `game_name_display` / 收敛迁移 0010，无 `GameStateRule`/`GameVersionCheck`/`MarketplaceItem` 字符串字段残留。
