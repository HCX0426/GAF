---
summary: GAF 待办路线图 — 项目级未完成项登记表 (P-NNN)
applies_to: [backend, frontend, agent, project]
last_updated: 2026-07-20
---

# GAF 待办路线图 (Pending Roadmap)

> **目的**: 项目级"未完成项"登记表。每轮 plan 实现完成后，AI 必须检查此文件并更新状态标记（project_rules.md §4.5 / §4.6 / §4.8.1）。
>
> **维护规则**:
> - 任何 plan 中标记为 [B] 后续 Phase 的项必须迁入本文件
> - 任何 plan 实现中发现的"非本轮范围"问题，按性质分别登记：
>   - 技术债务 → `docs/archive/tech-debt-README.md` (TD-NNN)
>   - 未实现功能 → 本文件 (P-NNN)
> - 完成后迁入 `docs/completed-features.md` (C-NNN)
> - 不允许"既不登记也不实现"的悬空状态
>
> **相关文件**:
> - 详细改进路线图: `docs/architecture/historical-plans/gaf-improvement-roadmap.md` (P0-P3 改进项, 2026-07-07 从 `.ai-memory/plan/` 迁入)
> - 技术债务登记表: `docs/archive/tech-debt-README.md` (TD-NNN)
> - 已完成功能清单: `docs/completed-features.md` (C-NNN)

## 状态标记

- ⏳ **待实现** — 已登记但未开始
- 🔧 **部分实现** — 有代码但未完整 / 未验证
- 🚧 **进行中** — 正在实现
- ✅ **已完成** — 已迁入 completed-features.md
- ⏸️ **暂缓** — 用户决定推迟，附理由
- ❌ **取消** — 评估后决定不做，附理由

---

## 活跃待办 (Active Pending)

| ID | 优先级 | 模块 | 项 | 状态 | 何时 | 关联 |
|:---|:------:|:----:|---|:----:|:----:|:-----|
| — | — | — | (Active Pending 表暂空 — spec-44 (P-012) 已完成迁入 Archived 段) | — | — | — |

---

## 待迁移项 (Items to Migrate)

> 以下为本轮 plan 实现中标记为 [B] 后续 Phase 的项，待迁入"活跃待办"表。

*（暂无 — 后续 plan 完成时填写）*

---

## Review Checklist (每轮 plan 实现完成后必跑)

AI 在每轮 plan 实现完成后，必须执行以下步骤：

1. **扫描本文件**: 读取所有 ⏳ 待实现 / 🔧 部分实现 / 🚧 进行中 状态的条目
2. **扫描 tech-debt/README.md**: 读取所有 🔧 待修 / 🚧 进行中 状态的条目
3. **挑 1-2 个高优先级项推进**: 优先 P0 > P1 > P2 > P3
4. **推进完成后更新状态**: ✅ 已完成 → 迁入 completed-features.md
5. **commit 时附 hash**: 在本文件对应条目记录 commit hash

**禁止行为**:
- ❌ 跳过本检查直接进入下一轮 plan
- ❌ 把"暂缓"项留作 ⏳ 状态超过 3 轮（要么推进，要么标 ❌ 取消附理由）
- ❌ 登记新项时不写"何时"字段

---

## 历史归档 (Archived — P-001~P-011 全部终态)

> 以下条目已全部完成或取消，保留用于历史参考。完成记录见 `docs/completed-features.md` (C-NNN)。

| ID | 模块 | 项 | 最终状态 | 完成时间 | 关联 |
|:---|:----:|---|:--------:|:--------:|:-----|
| P-001 | AI 能力 | R36 VLM 视觉驱动任务生成 | ❌ 取消 | 2026-07-11 | 用户决定不实现 |
| P-002 | 设备/数据治理 | R37-P0 BD2 窗口去重 Bug + DB 清理 | ✅ 已完成 | 2026-07-05 | C-008 (commit - + -) |
| P-003 | 模型架构 | R37-P1 归属 FK 重构 + 模板标注后端打通 | ✅ 已完成 | 2026-07-05 | C-009 (5 commits) |
| P-004 | 任务迁移 | R37-P2 BD2 任务迁移 + ROI 管理 UI + 导入 API 实装 | ✅ 已完成 | 2026-07-06 | C-011~C-014 (9 commits) |
| P-005 | 设备操作 UI | R37-P3 设备操作从 DeviceOperationPanel 迁移到标注界面 | ✅ 已完成 | 2026-07-05 | C-010 (4 commits) |
| P-006 | 引擎扩展 | pipeline schema 扩展（template_match_any + swipe_until 组合节点）| ✅ 已完成 | 2026-07-10 | 4 commits (TD-013 ✅ FIXED) |
| P-007 | 重构执行 | R37-P3 backend app 归一化 (Stage 6 + Stage 7) | ✅ 已完成 | 2026-07-08 | C-023 (9 commits) |
| P-008 | 重构执行 | R37-P3 遗留: Recording/TraceSpan/Pipeline/PipelineSnapshot 迁移 | ✅ 已完成 | 2026-07-09 | 3 commits (TD-060/061 ✅ FIXED) |
| P-009 | 任务调度 | 无人值守 TaskChain 4 Phase 渐进重构 (DB 持久化 + Celery beat 循环 + recovery 接入 + 多 session 并行) | ✅ 已完成 | 2026-07-14 | C-035 (`-`/`-`/`-`) |
| P-010 | 任务调度 | `handle_step_failure` 接入 — step 级失败信号 → recovery_engine | ✅ 已完成 | 2026-07-15 | C-037 (`-`/`-`/`-`) |
| P-011 | 任务调度 | 多 UnattendedSession 并行 — 按 game_profile 分组 | ✅ 已完成 | 2026-07-16 | C-039 (`-`/`-`) |
| P-012 | governance | spec-44: 月度检查瘦身 (G 类 8 项已迁自动 spec-41) | ✅ 已完成 | 2026-07-20 | C-071 (`-`) |
| P-013 | governance | spec-45: 月度检查自动化 (C1/H1/I1/N1 4 项迁自动 spec-45) | ✅ 已完成 | 2026-07-20 | C-072 (-) |
| P-014 | governance | spec-46: d4_path_drift evidence/ 降级 + GAF/ 前缀批量修复 | ✅ 已完成 | 2026-07-20 | C-073 (-) |
| P-015 | governance | spec-47: TD-279 lessons/summaries/platforms 路径漂移 3 轮批量修复 (P0 173→0) | ✅ 已完成 | 2026-07-20 | C-074 (-) |
| P-016 | governance | spec-48: P1 批量修复 (frontmatter 字段 + count drift + bloat, P1 27→0) | ✅ 已完成 | 2026-07-20 | C-075 (-) |
| P-017 | governance | spec-49: AI 自决框架加固 (5 层 7 项改进, 5 🟡 缺陷全修复) | ✅ 已完成 | 2026-07-20 | C-076 (-) |
| P-018 | governance | spec-50: d7 检查器范围修复 + P0 回归修复 (b_minus_a false positives 20→0, P2 70→50) | ✅ 已完成 | 2026-07-20 | C-077 (-) |
| P-019 | governance | spec-51: architecture-mistakes.md N## 冗余清理 (36 段落/2013 行删除) + thresholds.yaml glob 修复 (d2 P2 1→0) | ✅ 已完成 | 2026-07-20 | C-078 (-) |
| P-020 | governance | spec-52: 测试副作用残留清理 (conftest.py autouse fixture, resources/ untracked 残留清零) | ✅ 已完成 | 2026-07-20 | C-079 (-) |
| P-021 | governance | spec-53: L3-4 [B] 类纳入 + d4/d7 残留治理 (evidence/ 跳过 frontmatter + a_minus_c_whitelist + L3-4 增强, P2 49→0 飞轮读侧完全解锁) | ✅ 已完成 | 2026-07-20 | C-080 (-) |
| P-022 | governance | spec-54: TD-281 迁移 + plan-44 status 同步 + 5 新 TD 登记 (TD-287~291) + TD-292 顺便闭环 | ✅ 已完成 | 2026-07-20 | C-081 (-) |
| P-023 | a11y | spec-36: TD-270 aria-label 10 文件 14 处 + TD-272 PageWrapper 3 AI 页面 + TD-271 wontfix (审计后已响应式) | ✅ 已完成 | 2026-07-20 | C-082 (-) |
| P-024 | governance | spec-38: TD-282 hook 按 maintainer 模式差异化校验 + 22 lessons 删 maintainer 行回退 legacy | ✅ 已完成 | 2026-07-20 | C-083 (-) |
| P-025 | governance | spec-39: 小 TD 批量治理 — TD-278 generate-api-types 时间戳头 + TD-276/290/291 wontfix 审计 (EVALUATED) | ✅ 已完成 | 2026-07-20 | C-084 (-) |
| P-026 | governance | spec-40: TD-288 AgentSelector cleanup (lazy import + dead code + 34 单元测试) + TD-273 Phase 1 constants 模块 (dedup ComparisonOperator/LoopType) | ✅ 已完成 | 2026-07-20 | C-085 (-) |
| P-027 | governance | spec-41: TD-277 accounts→agents 跨 app import 解耦 via agents/services.py (5 service 函数 + 4 处调用改造 + is_agent_offline helper) | ✅ 已完成 | 2026-07-20 | C-086 (-) |
| P-028 | governance | spec-44: TD-273 Phase 2 agent 字符串字面量全量迁移到 enum (3 新 enum + 11 文件 50+ 比较点 + StrEnum 升级) | ✅ 已完成 | 2026-07-20 | C-087 (-) |
| P-029 | governance | spec-45: TD-291 screenshot_retention_gb wontfix 重新开放 + 实施 (cleanup_view retention 逻辑 + 6 单元测试, 用户授权方案 B) | ✅ 已完成 | 2026-07-20 | C-088 (-) |
| P-030 | governance | spec-42: TD-287 message_compressor 接入 AgentConsumer + agent ws_client 热路径 (Hello/Hello.ack 协商 + msgpack+zlib 压缩 + 端到端测试 12/12, 大修改 25/35 AI 自决) | ✅ 已完成 | 2026-07-20 | C-089 (-) |
| P-031 | governance | spec-43: TD-289 backend 22 处 except Exception 静默吞修复 (14 文件加 logger.warning + exc_info=True, 保留原 control flow; view 层具体异常迁移留 TD-293) | ✅ 已完成 | 2026-07-20 | C-090 (-) |
| P-032 | governance | spec-55: TD-293 view 层 except Exception 分级治理方案 C (A 类 1 处 scheduler/views.py:303 加 ValueError → 400 + B/C 类 40+ 处 logger.warning/error + exc_info 补漏, 117/117 except Exception 全有 logger; N167 31/35 AI 自决, 大修改) | ✅ 已完成 | 2026-07-20 | C-091 (-) |
| P-033 | governance | spec-56: L3-1 全量扫描 [A] 类批量修复 (protocol silent swallow 1 + agent enum 残留 5 + celery acks_late 3, 7 文件 +20 行; N167 32/35 AI 自决, 中修改; TD-294~299 登记 6 个 [B] 类) | ✅ 已完成 | 2026-07-20 | C-092 (-) |
| P-037 | governance | spec-59-A: AI 思维链纠偏 + 反思分级 + 元评估闭环 (N178 4 项 + N179 + N180, 3 项硬约束沉淀 rules §2.0.5+§4.6+§4.11; N167 32/35 用户授权; 元评估 9 项弱项 6 项本 spec 修 + 6 项登记 TD-302/303) | ✅ 已完成 | 2026-07-21 | C-095 (-) |
| P-038 | governance | spec-59-B (TD-302): 规则文档瘦身 v9.2 — B1 跳转链压缩 3 层 + B2 N151/N167 双处合并 + B3 L1/L2/L3 改名 LM1/LM2/LM3 (~150 行; P3) | ✅ 已完成 | 2026-07-21 | C-097 (commit -, B3 KEEP per N178-A3) |
| P-039 | governance | spec-59-C (TD-303): 工作流节奏调整 — C1 3 spec→2 spec + C3 hash 回填简化 + C4 测试策略归一 + D1 规则退役 + D2 TD 登记 ≤ 3 (~150 行; P3) | ✅ 已完成 | 2026-07-21 | C-098 (commit -, N167 14/15 用户授权 A 调整版) |
| P-040 | governance | spec-59-D (TD-298): N170/N165 规则退役 (N181 首次执行 — §Active→§Retired + §Dormant N165 行删除) | ✅ 已完成 | 2026-07-21 | C-099 (commit -, 小修改豁免 N167) |
| P-041 | governance | spec-59-E (TD-297): 集成层一致性治理 — raw SQL→ORM (3 处) + 跨 app import→service/lazy (gaf_ai/services.py 4 函数 + executions apps.get_model) + FrontendEventType.NOTIFICATION 常量 + spec_id 冲突 N178-A3 KEEP (中修改 ~170 行; N167 14/15 用户授权 A 激进; N177 全套 1609 passed in 361s) | ✅ 已完成 | 2026-07-21 | C-100 (-) |
| P-042 | governance | spec-60 (TD-307): failure-modes.md P5 阈值调整 150→170 + 代码常量 FAILURE_MODES_MAX_LINES 120→170 同步 (enforce-limits dry-run 无可归档候选, Active N## 全被引用, 数量以 sync_ai_memory 动态计数为准) + 登记 TD-312 (promote_lessons.py 2 bug: line_count 含 frontmatter + 常量无同步机制); 小修改 ~10 行; body 163 ≤ 170 margin -7) | ✅ 已完成 | 2026-07-21 | C-101 (-) |
| P-043 | governance | spec-63 (TD-304): 前端 raw fetch 鉴权 + URL 漏洞修复 — DailySummaryCarousel.tsx 加 buildAuthHeaders (后端 IsAuthenticated 401 静默吞) + InfraHealthPanel.tsx 修 URL `/api/system/health/` → `/api/v2/accounts/init/health/` + 加 buildAuthHeaders (URL 404 永远 unavailable); 小修改 < 50 行 (与 H12 修复模式一致, 不迁 axios client) | ✅ 已完成 | 2026-07-21 | C-102 (-) |
| P-035 | governance | spec-58-A: TD-296 spec A cleanup_view atomic + IntegrityError + transaction.atomic (5 处关键写, 4 文件 +60 行; N167 34/35 AI 自决, 中修改; N177 分级测试 accounts+tasks+settings 218 passed in 82s; 元评估沉淀 "测试时间越来越久了" → §4.9 N177 分级测试策略) | ✅ 已完成 | 2026-07-21 | C-094 (-) |
| P-036 | governance | spec-58-B (TD-301): celery task retry 补齐 (12 处 @shared_task 加 max_retries=3 + retry_backoff, select_for_update 5 处 KEEP 审计; N167 30/35 用户授权, N177 分级测试 573 passed in 123s; TD-296 全闭环) | ✅ 已完成 | 2026-07-21 | C-096 (-) |
| P-034 | governance | spec-57: TD-295 后端 RBAC + DB 性能治理 (RoleBasedPermission 10 + DB index 3 + TextField max_length 1 + N+1 select_related 5, 12 文件 +60 行; 7 处个人操作 KEEP; N167 35/35 AI 自决, 中修改; TD-300 登记 N+1 剩余 41 处) | ✅ 已完成 | 2026-07-20 | C-093 (-) |

### R37 — 数据模型归属重构与 BD2 数据治理（已完成）

> **来源**: 2026-07-05 用户提出的整体方案评估。用户观察到设备列表出现 4 个 BrownDust II 重复窗口，并质疑当前 ResourcePack/Task/Window 归属关系不清晰。经 4 路并行调研后确认：BD2 窗口去重逻辑缺失 + 资源包/任务/窗口归属游戏档案的 FK 链断裂 + 模板标注界面后端未打通 + 11 个 BD2 任务未迁移。
>
> **用户决策**（2026-07-05）:
> 1. ResourcePack 加 FK 到 GameProfile，**保留** GameAccount.resource_pack 引用（换服灵活性）
> 2. Device/Window 的 game_profile FK 为 **nullable**（兼容未识别窗口）
> 3. example_game 2 个示例任务（daily_sign_in.yaml / stage_battle.yaml）**保留禁用**，不删除
> 4. 分 P0/P1/P2 三阶段推进

**R37 整体验收**（全部 ✅）:
- BD2 窗口在设备列表中只显示 1 条
- 资源包/任务/窗口都明确归属到 BrownDust II GameProfile
- 模板标注界面数据持久化到后端
- 任务管理 UI 显示游戏/资源包/模板/设备归属
- 11 个 BD2 任务可执行
- v9.0 二分制分发完成
