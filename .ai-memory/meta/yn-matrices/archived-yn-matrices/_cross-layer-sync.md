---
summary: 路径漂移/前后端字段同步 Y/N 矩阵 — 路径一致性/后端字段→前端4步配套
applies_to: [path-consistency, frontend-backend-sync, reflection]
last_updated: 2026-07-18
source: Split from yn-matrices.md (Phase 4 Task 4.2)
---

## §4 cross-layer-sync — 路径漂移/前后端字段同步

### ⑧ N106 路径一致性 Y/N 矩阵（必填，M1.A.1 加项）

> **触发条件**（任意一条即触发）:
> - 修改了带 `路径` / `Path` / `JSON` / `YAML` 写入的代码
> - 跑通了 sync 工具但 `git status` 没变化（gitignore 漂移）
> - spec.md / docs/ 写明的文件路径与代码 inline 拼路径不一致

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | spec/docs 写明的文件路径, 代码用**模块级常量** (非 inline) | | `grep -E "Path\(\)\|/" <file> \| grep -v SYNC_STATE \| grep -v CONST` |
| 2 | sync 工具跑通 ≠ 路径正确, 必须 `Test-Path` 双重检查 | | `Test-Path <expected_path>` |
| 3 | gitignore 的文件不靠 git status 验证, 必须 `ls` 或 `Test-Path` | | `ls <expected_path> && ! ls <wrong_path>` |
| 4 | v9.0 二分制分发需双向验证 (spec ↔ code), 单向分发不够 | | 反思清单 ⑥ Y/N 全部填 ✅ |

**AI 必做**:
- ✅ 任何 spec 写明路径的文件 → 代码必须用模块级常量 (避免 inline 漂移)
- ✅ 改路径后立即 `Test-Path` 双向验证 (期望路径存在 + 错误路径不存在)

**预防规则**（N106 提取）:
- `state_path = root / ".ai-memory" / "sync-state.json"` → 改用 `state_path = SYNC_STATE if root == REPO_ROOT_DEFAULT else root / ".ai-memory" / "sync-state.json"`
- 模块顶部定义 `SYNC_STATE = AI_MEMORY / "sync-state.json"` 作为 single source of truth
- pre-commit hook 可加 `gaf-path-consistency-check` 扫 inline 拼路径 (M1.A 后续)

**反模式家族**: N95 (分级分发) + N96 (L2 跳过) + N100 (Set-Content 损坏) + **N106 (路径漂移)** —— 同根因 (验证缺位)

### ⑪ N112 后端字段变更 → 前端 4 步配套 Y/N 矩阵（必填，P-024-4 闭环加项）

> **触发条件**（任意一条即触发）:
> - AI 改 backend model 字段 (增/改/删字段)
> - AI 改 backend serializer fields
> - AI 改 backend views action (新增/修改端点)
> - 用户反馈 "前端跟后端对不上" / "点了没反应" / "标签显示不出来"

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | Read backend serializer (字段权威源) | | `Read backend/<app>/serializers.py` |
| 2 | Read backend views (action 端点 + 错误码) | | `Read backend/<app>/views.py` |
| 3 | Grep 现有 TS 类型对比 | | `Grep frontend/src/types/models.ts <field>` |
| 4 | TS 类型同步 (新字段/类型) | | `frontend/src/types/models.ts` 改动 |
| 5 | API client 真实调用 (移除 placeholder) | | `frontend/src/api/<app>.ts` 改 `client.post/put` |
| 6 | UI 标签 + 颜色 (severity 4级等) | | `frontend/src/pages/<Page>.tsx` 改 render |
| 7 | 过滤下拉 + 静默提示 (字段全覆盖) | | `Select options={[]}` 含新字段 |
| 8 | `dataIndex` 严格对齐后端字段名 | | `Grep "dataIndex" frontend/src/pages/` |
| 9 | acknowledge 等错误码处理 (409 等) | | `catch (err)` + `axiosErr.response.status` |
| 10 | tsc 编译通过 | | `npx tsc --noEmit` exit 0 |

**AI 必做**:
- ✅ 4 步配套: TS 类型 / API client / UI 标签 / 过滤下拉 — 缺一不可
- ✅ 写前端前 3 步: Read serializer → Read views → Grep 现有 TS
- ✅ `dataIndex` 必须 = 后端 serializer `fields` 列表中的字段, 禁止凭语义编
- ✅ severity 4 级颜色: P0 red / P1 orange / P2 gold / P3 blue (P-024 一致性)
- ✅ acknowledge 错误码 409: `msg.warning` + 重新拉取, 不用 `msg.error`
- ❌ NEVER 留 API placeholder (`Promise.resolve()`) 假装已实现 (违反 N101)
- ❌ NEVER 凭语义编 `dataIndex` (如 `rule`/`details`/`resolved`), 必须 Read serializer
- ❌ NEVER severity 3 级 (info/warning/critical) 与后端 4 级 (P0-P3) 错配
- ❌ NEVER 改后端字段后跳过前端 4 步配套 (用户后果: 标签失效 / 点了没反应)

**预防规则**（N112 提取）:
- 改后端 → 必须把前端 4 步 (TS/API/UI/Filter) 加到本轮 todo
- 写前端前 → 必跑 3 步核对 (Read serializer / Read views / Grep TS)
- 提交前 → 必跑 tsc + audit + v9.0 二分制分发
- 同根因家族: N95 (分级分发) + N101 (状态不诚实) + N106 (路径漂移) + N112 (跨层同步)

### N152 DRF 全局分页 vs 前端数组期望 Y/N 矩阵（必填，日志中心白屏）

> **触发条件**（任意一条即触发）:
> - 新增/修改 DRF ViewSet 且项目启用了 `DEFAULT_PAGINATION_CLASS`
> - 前端 fetch helper 声明返回 `T[]` 而非 `PaginatedResponse<T>`
> - 用户反馈表格/列表白屏，控制台 `TypeError: xxx.some is not a function`

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证命令 |
|:-:|--------|:---:|----------|
| 1 | ViewSet 显式声明 `pagination_class`（None 或具体类） | | `Read backend/<app>/views.py` |
| 2 | 后端 list 返回形状与前端 TS 类型一致 | | 对比 `client.get<T>` 与 ViewSet/serializer |
| 3 | 组件取数时按实际形状处理（`res.results` 或 `res`） | | `Grep "fetch.*Logs\|setData" frontend/src/pages/` |
| 4 | 测试不“兼容两种形状”，而是断言真实契约 | | `Grep "results" backend/<app>/tests/` |
| 5 | 浏览器验证 list/table 可正常渲染 | | Playwright / browser-use 点击验证 |

**AI 必做**:
- ✅ 新增 ViewSet 时立即决定分页行为：数组 → `pagination_class = None`；分页 → 前端用 `PaginatedResponse<T>`
- ✅ 后端、前端类型、组件取数三者保持一致
- ✅ 禁止测试同时兼容 list 和 paginated dict 来掩盖契约不明确
- ❌ NEVER 让全局默认分页隐式决定 API 返回形状
- ❌ NEVER 把 paginated 对象直接传给 `dataSource={res ?? []}`

**预防规则**（N152 提取）:
- 项目启用全局 DRF 分页时，每个 ViewSet 必须显式配置 `pagination_class`
- 写前端 API client 前，先用 `curl`/Playwright/DRF browseable API 确认真实返回形状
- 表格组件白屏时优先检查 `dataSource` 是否为数组

---

