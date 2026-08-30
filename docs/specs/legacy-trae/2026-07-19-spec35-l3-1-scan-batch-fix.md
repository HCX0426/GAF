# spec-35: L3-1 全量扫描 [A] 类批量修复 (10 项)

> **来源**: 2026-07-19 L3-1 全量扫描 (用户 explicit "再全量扫描") — 3 subagent 并行扫描 9 维度发现 10 个 [A] 类问题
> **决策**: 用户选 "全部 [A] 开 spec-35 (推荐)" — 单 spec 4 Phase 覆盖全部 [A] 类
> **状态**: ✅ Done (2026-07-19)

## 阶段状态表

| Phase | 内容 | 优先级 | 行数估计 | 状态 | 完成时间 | Commit | 验收 evidence |
|:-----:|------|:------:|:--------:|:----:|:--------:|:------:|--------------|
| 1 | 文档状态同步 (4 项: spec-27 + spec-33 + C-011) | P3 | ~8 | ✅ | 2026-07-19 | - | spec-33 header ✅ Done; spec-27 commit hash 回填 + Phase 4 heading 修正 + ⏳→TD-269; C-011 🔧→✅ |
| 2 | 后端状态校验 + Agent handle_error 死代码 (2 项) | P2 | ~15 | ✅ | 2026-07-19 | - | backend/agents + agent client: 113 tests passed |
| 3 | 前端 NodePropertyPanel required 校验 (1 项) | P1 | ~30 | ✅ | 2026-07-19 | - | 12 个 Form.Item 加 rules; tsc 0 errors |
| 4 | 协议漂移 + 死 WS 清理 (5 项, 大量删除) | P1 | ~370 删 | ✅ | 2026-07-19 | - | backend 363 tests + agent 1554 tests passed; spectacular 0 errors+0 warnings; vite build OK |

**总计**: 10 项 [A] 类, ~423 行 (大部分是删除)

## Phase 1: 文档状态同步 (4 项 P3)

### 1.1 spec-33 header 状态陈旧
- **文件**: `.trae/specs/2026-07-18-spec33-ai-workflow-slim.md:3`
- **问题**: header `**状态**: 🔄 进行中` 但 6 个 Phase 全 ✅ (L12-17), acceptance criteria checkboxes (L100-106) 仍 `[ ]`
- **修复**: header → `✅ Done`, 勾选 acceptance criteria checkboxes

### 1.2 spec-27 Phase 1-3 commit hash 缺失
- **文件**: `.trae/specs/2026-07-18-spec27-folder-reorganization.md:11-13`
- **问题**: Phase 1-3 标 ✅ 但 commit 列写 "(待 commit)", 从未回填
- **修复**: `git log --oneline --grep="spec-27"` 找 commit hash 回填

### 1.3 spec-27 Phase 4 heading 陈旧
- **文件**: `.trae/specs/2026-07-18-spec27-folder-reorganization.md:59`
- **问题**: heading `## Phase 4: 同步更新待办 (🔄 进行中)` 但状态表 L14 显示 ✅
- **修复**: 移除 `(🔄 进行中)`

### 1.4 spec-27 dangling ⏳ spec-32 引用
- **文件**: `.trae/specs/2026-07-18-spec27-folder-reorganization.md:115`
- **问题**: "⏳ 跨文件路径引用待 spec-32 统一更新" 但 spec-32 不存在 (当前 spec-25..spec-34, 无 spec-32)
- **修复**: 改为登记到 `docs/general/tech-debt/active.md` 作为 TD-269 (spec-32 文档治理待定), 移除 ⏳ 标记

### 1.5 C-011 状态陈旧
- **文件**: `docs/general/completed-features.md:44,194`
- **问题**: spec-28 (2026-07-18, Phase 6 ✅) 已声明 `C-011 ✅` 但 completed-features.md 仍标 🔧
- **修复**: L44 `🔧` → `✅`, L194 `🔧 部分完成` → `✅ 完成`

### Phase 1 验收
- [x] spec-33 header + checkboxes 更新
- [x] spec-27 Phase 1-3 commit hash 回填 + Phase 4 heading 修正 + ⏳ 改为 TD-269 引用
- [x] completed-features.md C-011 升级为 ✅
- [x] git diff 检查所有变更范围

## Phase 2: 后端状态校验 + Agent handle_error 死代码 (2 项 P2)

### 2.1 Device.update_status() 缺状态校验
- **文件**: `backend/agents/models.py:412-419`
- **问题**: `def update_status(self, new_status: str)` 接受任意字符串, 不验证 `Device.Status.choices` (`online`/`offline`/`busy`/`error`)
- **修复方案 A (推荐)**: 改签名为 `new_status: Device.Status` (enum 类型注解), Python 3.x + Django 接受 enum 值
- **修复方案 B (运行时校验)**: 加 `if new_status not in Device.Status.values: raise ValueError(...)`
- **倾向**: 方案 A (类型注解 + IDE/mypy 提示, 不加运行时开销)
- **测试**: 跑 `backend/agents/tests/` 验证无回归

### 2.2 Agent handle_error 死代码
- **文件**: `worker/src/client/connection.py:568` + `worker/src/client/handler.py:159`
- **问题**: backend spec-29c 已移除 `"error"` type, 改用 `agent.status` + `status=error`. agent 的 `handler_map` 仍含 `"error": handler.handle_error` 条目 + `handle_error` 方法, 永远不会被调用
- **修复**:
  - 删除 `connection.py:568` 的 `"error": handler.handle_error` 条目
  - 删除 `handler.py:159` 的 `handle_error` 方法
  - 检查 `handle_status_update` 是否已 branch on `status == "error"` (若未, 加上)
- **测试**: 跑 agent 单元测试 + 验证 backend 发 `agent.status` + `status=error` 时 agent 正确处理

### Phase 2 验收
- [x] `Device.update_status` 签名改为 enum 或加运行时校验
- [x] agent `handle_error` + handler_map 条目删除
- [x] backend agents tests 全 pass
- [x] agent client tests 全 pass (113 tests passed)

## Phase 3: 前端 NodePropertyPanel required 校验 (1 项 P1)

### 3.1 9 个 required 字段缺 `rules` 校验
- **文件**: `frontend/src/components/Pipeline/NodePropertyPanel.tsx:149,224,363,388,456,514,570,596,689`
- **问题**: `renderRequiredLabel('模板'/'目标坐标'/'按键'/'文本'/'条件表达式'/'目标节点'/'监控规则'/'Pipeline'/'模型路径')` 显示红 ✱, 但对应 `Form.Item` 缺 `rules={[{ required: true }]}`. 用户可提交空值
- **修复**: 给每个 `Form.Item` 加 `rules={[{ required: true, message: '<字段名>不能为空' }]}`. 保留 `renderRequiredLabel` 视觉提示
- **验证**:
  - `cd frontend; npx tsc --noEmit` 0 errors
  - 手动测试: 清空 required 字段后提交, 应被拦截
  - 若有 Vitest 测试, 跑 `npm test -- NodePropertyPanel`

### Phase 3 验收
- [x] 12 个 `Form.Item` 加上 `rules` (原估 9 个, 实际 12 个含 click/long_press/start_app/stop_app 重复 label)
- [x] tsc --noEmit 0 errors
- [ ] (可选) 浏览器手动验证

## Phase 4: 协议漂移 + 死 WS 清理 (5 项 P1)

### 4.1 Dead WS `/ws/executions/{id}/` 清理
- **文件**:
  - `backend/executions/routing.py:14` (URL pattern)
  - `backend/executions/consumers.py:24` (`ExecutionConsumer` class)
  - `backend/tasks/signals.py:172,188` (`broadcast_execution_update` calls)
  - `backend/config/asgi.py:22-27` (WS routing registry)
- **问题**: 后端有 consumer + signal 广播, 前端 0 引用 (grep `ws/executions` in `frontend/src` = 0 matches). 所有 execution 更新被丢弃
- **修复**:
  - 删除 `executions/routing.py` 的 executions WS pattern
  - 删除 `executions/consumers.py` 的 `ExecutionConsumer` class
  - 删除 `tasks/signals.py` 的 `broadcast_execution_update` 调用 (保留 signal 本身, 只删 broadcast)
  - 更新 `config/asgi.py` 移除 executions routing
- **验证**: backend pytest `executions/tests/` + `tasks/tests/` 全 pass

### 4.2 Dead WS `/ws/devices/{id}/screenshot-stream/` 清理
- **文件**:
  - `backend/agents/routing.py:9` (URL pattern)
  - `backend/agents/consumers.py:22` (`ScreenshotStreamConsumer` class)
  - `backend/config/asgi.py` (WS routing registry)
- **问题**: 前端 `useScreenshotStream` 用 dashboard WS 接收截图帧 (`WS_EVENT.SCREENSHOT_FRAME`), 此 consumer 死代码
- **修复**:
  - 删除 `agents/routing.py` 的 screenshot-stream pattern
  - 删除 `agents/consumers.py` 的 `ScreenshotStreamConsumer` class
  - 更新 `config/asgi.py` 移除 screenshot-stream routing
- **验证**: backend pytest `agents/tests/` 全 pass

### 4.3 Agent `"device.screenshot"` 协议漂移
- **文件**:
  - `worker/src/client/handler.py:602,625,636,646,656` (5 处发送 `"device.screenshot"`)
  - `backend/protocol/constants.py:14-56` (`MessageType` enum 不含)
  - `backend/protocol/serializers.py:19` (`ChoiceField(choices=MessageType.all_types())` 会拒绝)
- **问题**: agent 发送的 frame 类型 backend 不识别, `MessageFrameSerializer` 拒绝 + `AgentConsumer._handle_unknown` 返回 error frame
- **修复路径选择**:
  - **A (推荐)**: 删除 agent `handle_device_command` 方法 (item 4.4 一起处理), 则 `"device.screenshot"` 自动消失
  - **B**: 加 `DEVICE_SCREENSHOT = "device.screenshot"` 到 `MessageType` (若需要保留功能)
- **倾向**: A (与 4.4 合并, agent orphan handler 是死代码)

### 4.4 Agent 孤立 handler `handle_device_command` + `handle_config_update`
- **文件**:
  - `worker/src/client/handler.py:591` (`handle_device_command`)
  - `worker/src/client/handler.py:664` (`handle_config_update`)
  - `worker/src/client/connection.py:554-569` (`handler_map` 9 个 type, 不含 `device.command` / `device.action` / `config.update`)
- **问题**: `handler_map` 未引用这两个方法, backend `MessageType` 不含对应 type, backend 无法发送. 死代码
- **修复**:
  - 删除 `handler.py:591` 的 `handle_device_command` 方法
  - 删除 `handler.py:664` 的 `handle_config_update` 方法
  - 检查是否有其他引用 (`grep handle_device_command handle_config_update agent/`), 若有也清理
- **验证**: agent client tests 全 pass

### 4.5 (与 4.3+4.4 合并) Agent handle_error + "error" type — 已在 Phase 2.2 处理
- Phase 4 不重复, Phase 2.2 已修

### Phase 4 验收
- [x] `executions/consumers.py` `ExecutionConsumer` 删除 (整个文件删除)
- [x] `agents/consumers.py` `ScreenshotStreamConsumer` 删除
- [x] `worker/src/client/handler.py` `handle_device_command` + `handle_config_update` 删除
- [x] `backend/protocol/constants.py` `MessageType` 不含 `device.screenshot` (因为 agent 不再发送)
- [x] `tasks/signals.py` `broadcast_execution_update` 调用删除
- [x] `config/asgi.py` WS routing 注册表更新
- [x] backend pytest 全 pass (363 tests)
- [x] agent 单元测试全 pass (1554 tests + 2 skipped)
- [x] `spectacular --validate --fail-on-warn` 仍 exit 0 (协议变更不影响 schema)

## 全量回归 (Phase 1-4 完成后)

- [x] `spectacular --validate --fail-on-warn` exit 0
- [x] backend pytest 全套 pass (363 tests: agents/executions/tasks/protocol)
- [x] agent pytest 全套 pass (1554 tests + 2 skipped)
- [x] `cd frontend; npx tsc --noEmit` 0 errors
- [x] `cd frontend; npx vite build` 成功 (19.54s)
- [ ] (可选) browser-use 启动 backend+frontend+agent, 验证 task execution 流程 + screenshot stream 仍工作 (因为 dashboard WS 接管)
- [x] commit + 更新 completed-features.md C-063

## [B] 类登记 (spec ✅ 后)

把 10 项 [B] 类登记到 `docs/general/tech-debt/active.md`:
- TD-270: aria-label 覆盖不全 (P2)
- TD-271: 响应式设计缺失 (P2)
- TD-272: PageWrapper 覆盖审计 (P3)
- TD-273: 字符串字面量状态比较 (P3)
- TD-274: monitors/views.py 冗余 pass (P3)
- TD-275: migration 一致性验证 (P2)
- TD-276: executions/views.py:45 N+1 风险 (P3)
- TD-277: accounts/views.py 跨 app 前向 import (P3)
- TD-278: api.generated.ts 缺生成时间戳 (P3)
- TD-279 (= TD-251 复活): spec-32 文档治理 (P3, >500 行)

## L3-4 终止条件检查

spec-35 ✅ 后:
- 连续 1 轮扫描 + 修复 (本轮)
- 下一轮 L3-1 扫描 (Round 2) 检查是否新增 [A] 类
- 满足任一终止条件即停: 连续 2 轮无新增 [A] / 所有 [A] 已修 + [B] 已登记 / 上下文预算告警 / 用户叫停
