# GAF 情境硬约束（按需加载载体 — 由 env-hardrules.md L0 迁出）

> 本文件承载 \env-hardrules.md\ (L0) 迁出的**情境触发**硬约束，不常驻系统提示。
> 由 \gaf-orchestrator\ 在 task_type ∈ {fix, new_feature, refactor, documentation} 或触发关键词命中时 \Read\ 对应段。
> 各段触发条件与映射见 \env-hardrules.md\ 文末「情境硬约束索引」。本文件即 failure-modes / handbook 中 N191-N204 详细检查清单的权威载体。


## Schema 归一化硬约束 (N191)

> **状态**: 活跃 — 由 orchestrator 触发加载，非 L0 常驻

> 触发场景: **schema 归一化类重构** (字段重命名 / 嵌套结构变更 / 字段合并 / schema 版本升级 / 执行模式统一)。
> 根因: schema 重构 ≠ 代码重构 — schema 是全链路数据契约, 任何一端不归一化都断流。AI 完成 spec 阶段后默认任务完成, 不主动跑数据流全链路扫描, 用户多次提示才完成。

### 触发条件 (任一即触发)

- 任务涉及: schema 字段重命名 (如 `action_type` → `node_type`) / 嵌套结构变更 (如 `retry_count+retry_interval` → `retry: {max_retries, base_delay}`) / 执行模式统一 (如 `chain` → `pipeline`) / schema 版本升级
- 任务涉及: task_definition / params_config / pipeline_json / 节点 config 结构变更
- 任务涉及: 跨前后端 + agent 三方共享的数据契约修改

### 完成前必跑: 数据流全链路扫描 (7 项检查清单)

```text
□ 1. 数据流全链路识别: 列出 schema 的所有输出端 (前端编辑器/API 写入/外部导入/template.json) 和所有读取端 (后端校验/agent 解析/工具推断/测试数据/文档示例)
□ 2. 输出端 grep 扫描: 用旧 schema 关键字段 grep 全仓, 标记每处残留
□ 3. 读取端 grep 扫描: 用旧 schema 关键字段 grep 后端 + agent, 标记每处残留
□ 4. 类型定义审查: 前端 TS 接口 / 后端 serializer / agent dataclass 是否仍含旧字段
□ 5. 测试数据审查: 测试 fixture 是否仍用旧 schema
□ 6. 文档/资源审查: docs/business/ 文档示例 + resources/*/custom_tasks/template.json 是否仍用旧 schema
□ 7. 端到端验证: 用真实数据从前端编辑器跑到 agent 执行, 确认全链路无 schema mismatch
```

### 5 个 grep 模式 (覆盖扫描)

```bash
# 1. 旧字段名输出端 (前端) — 以 chain schema 为例
rg "action_type|next_step|retry_interval|fallback_action" frontend/src

# 2. 旧 schema 顶层字段 (task_definition 输出)
rg "task_definition.*steps|params_config.*steps"

# 3. 后端读取旧字段
rg "task_definition\.get\(.steps.\)|task_definition\[.steps.\]" backend

# 4. agent 读取旧字段 (排查 node_type 别名是否覆盖全)
rg "step\.get\(.action.\)|step\.get\(.type.\)|step\.get\(.node_type.\)" agent

# 5. 资源/文档旧 schema
rg "\"mode\":\s*\"chain\"|execution_mode.*chain" resources docs
```

### 节点间数据流检查 (识别→匹配→点击等节点链路)

```text
□ publish_match_pos 写入字段 (x, y, source, extra) 与 resolve_target 读取字段一致 (期望 dict 含 x/y 或 center.x/y 或 list/tuple)
□ 坐标系统标注: 节点 result_data 是否含 coord_system 字段 ("logical" / "physical" / "sub-image")
□ 坐标系统传递: 写入端 logical → 读取端期望 logical (WindowsDevice.click) 或 physical (ADBDevice)
□ ROI 偏移传递: 节点内部 crop 子图后, publish 的坐标是否加回了 ROI 原点偏移 (常见 bug 点)
□ 变量引用契约: set_variable 写入的 dict 结构是否满足 _extract_xy 的解析要求 (含 x/y 或 center.x/y)
□ None 兜底: publish_match_pos 的 x/y 不能是 None (publish_match_pos 已强制 int(x), 但调用方需保证非 None)
```

### 失败模式（禁止）

- ❌ 只改执行引擎 + 数据迁移, 不扫描前端编辑器输出端 → ✅ 全链路 7 项检查
- ❌ 只改代码, 不改 resources/*/custom_tasks/template.json 模板 → ✅ 资源文件同步归一化
- ❌ 只改代码, 不改 docs/business/ 文档示例 → ✅ 文档同步归一化
- ❌ spec 阶段全部 ✅ 就认为任务完成 → ✅ 必须跑端到端验证 (前端编辑器 → backend 存储 → agent 解析执行)
- ❌ 节点内部 crop 子图后 publish 子图坐标, 不加 ROI 偏移 → ✅ publish 全图坐标 (子图坐标 + ROI 原点偏移)
- ❌ 检查清单只写 lesson (L3 按需加载, AI 不主动读) → ✅ 已迁出至 env-hardrules-contextual.md (由 orchestrator 触发加载, 非 L0 常驻)

### 详细检查清单位置

- 完整检查清单见本文件 §Schema 归一化硬约束 (N191) (failure-modes 历史引用的 `lessons/N191-...md` 未单独创建, 本载体为其权威源)
- L1 索引: `meta/failure-modes.md` N191 行
- 触发本约束的任务: 在 `gaf-orchestrator` 决策树 step_1 标记 `task_type=refactor` + 涉及 schema 修改时, 主动加载本段

## 双调试视角硬约束 (N192)

> **状态**: 活跃 — **L0 强制常驻提醒**（每次对话注入，见 env-hardrules.md §L0 强制常驻提醒）+ 详细清单按需 Read

> 触发场景: **任何写代码 / 架构改动 / 重构 / 新增功能 / bug 修复** 任务。
> 根因: AI 默认只从「代码正确性」单视角检查 (函数跑得通、契约对得上、异常有兜底), 但 GAF 是「前端编辑器 → backend → agent 执行」三方协作系统, 代码正确 ≠ 可调试。必须同时从「AI 自己跑 pipeline 时能否定位问题」和「用户在 UI 上能否看懂错误」两个视角复查, 否则: agent 报错时堆栈截断、中间结果不落盘 → AI 反复加 log 才能定位; 用户配置出错时后端报错原文甩到前端 → 用户看不懂只能截图问开发。

### 触发条件 (任一即触发)

- 任何 `task_type=fix / add / refactor` 类任务完成前
- 修改了 pipeline 执行链路 / 节点 result_data / 错误处理 / 日志输出 / 前端错误提示 任意一项
- 架构改动涉及跨进程边界 (agent ↔ backend ↔ frontend) 的数据传递或错误传播

### 视角 A: AI 调试视角 (agent 自己跑 pipeline 时能否定位问题)

```text
□ A1. 报错可读性: 异常 raise 时是否含 节点 id / 输入参数 / 失败原因 三要素? 还是只有 traceback?
□ A2. 中间结果落盘: 节点 result_data 是否完整写入 (含 coord_system / source / extra)? 还是只 publish 部分字段?
□ A3. 日志分段: pipeline 执行日志是否按 节点 boundary 分段? 是否能从日志快速定位「卡在第几个节点」?
□ A4. 节点链路可追溯: 失败时能否回溯 上一个节点的输出 → 当前节点输入 的完整数据流?
□ A5. retry/fallback trace: 重试 / 降级路径是否留 trace (attempt N / fallback triggered)?
□ A6. 截断保护: 长字符串 / 图像数据 / 大 dict 在日志和 result_data 中是否合理截断而非全量打印?
□ A7. 报错边界: 节点内部异常是否被捕获并包装成「节点级失败」而非让整个 pipeline 崩?
```

### 视角 B: 用户调试视角 (用户在前端编辑器配置任务时能否看懂错误)

```text
□ B1. 错误提示归一: 后端校验失败 / agent 执行失败 的报错是否转换为用户可读文案? 还是原文 `KeyError: 'steps'` 甩到前端?
□ B2. 错误码映射: 是否有 error_code → user_message 映射表? 同一错误码在前端展示一致文案?
□ B3. 错误定位: 用户能否在 UI 上看到「第几个节点 / 哪个字段 / 什么输入 / 为什么不合法」?
□ B4. 模板可跑通: resources/*/custom_tasks/template.json 是否能让用户照着改就能跑通? 还是改完就报 schema 错?
□ B5. 校验前置: 前端是否有 schema 校验拦截 (避免提交后才发现配置错)?
□ B6. 执行反馈: 任务执行失败后, UI 是否展示 节点链路 + 失败节点高亮 + 失败原因?
□ B7. 复现路径: 用户拿到错误后能否自行复现 / 自行修复? 还是必须找开发查日志?
```

### 完成前必跑: 双视角复查清单

```text
□ 1. 代码改动涉及异常路径? → 跑视角 A 全部 7 项
□ 2. 代码改动涉及前端 / schema / 错误处理? → 跑视角 B 全部 7 项
□ 3. 跨进程边界改动 (agent ↔ backend ↔ frontend)? → A + B 都跑
□ 4. 自问: "如果 agent 这段挂了, 我加 log 能定位吗?" → 不能则补 trace
□ 5. 自问: "如果用户配置错了这段, 他能看懂提示吗?" → 不能则补 error_code 映射
```

### 失败模式（禁止）

- ❌ 写完代码只验「跑得通」, 不验「报错时可定位」 → ✅ 跑视角 A 清单
- ❌ 异常 raise 只带 message, 不带节点 id / 输入上下文 → ✅ 包装成 NodeExecutionError 含 context
- ❌ 后端校验失败直接 raise ValidationError, 前端拿原文展示 → ✅ error_code → user_message 映射
- ❌ 改了 schema 不改前端校验 / 不改错误提示 → ✅ 视角 B 同步归一化
- ❌ 中间节点 result_data 只 publish 成功路径, 失败路径不落盘 → ✅ 失败也落盘 (含 error 字段)
- ❌ 检查清单只写在脑里 / 只写在 PR 描述 → ✅ 已迁出至 env-hardrules-contextual.md (由 orchestrator 触发加载, 非 L0 常驻)

### 详细检查清单位置

- L1 索引: `meta/failure-modes.md` N192 行
- 触发本约束的任务: 在 `gaf-orchestrator` 决策树 step_1 标记 `task_type=fix/add/refactor` 时, 主动加载本段
- 与 N191 关系: N191 关注 schema 数据流「契约对齐」, N192 关注「报错可调试」, 二者互补不替代

## 任务归属硬约束 (N193)

> **状态**: 活跃 — 由 orchestrator 触发加载，非 L0 常驻

> 触发场景: **任何 spec/plan 驱动的任务** (有 spec 文档 + 任务清单 + 阶段化实现)。
> 根因: AI 在 spec 阶段全部 ✅ 后默认任务完成, 把实现过程中发现的优化建议/新问题作为"遗留建议"抛给用户决定, 而非自动纳入当前 spec 并实现。用户被迫二次确认才能让 AI 做本应在本次任务内完成的事, 优化建议容易丢失。

### 核心约束

1. **当前任务中发现的所有问题归属当前任务**: 实现过程中发现的优化建议、新 bug、schema 不一致、测试缺口、文档过时等, **必须立即纳入当前 spec** (新增 task / 扩展现有 task), 不能作为"遗留建议"抛给用户。
2. **spec 阶段全部 ✅ ≠ 任务完成**: 任务完成的真实定义 = spec 全部实现 **AND** 发现的问题全部处理 (实现或显式降级为 P4+ 并记录到 spec 的"已知限制"段)。AI 在 spec 完成 + 测试通过后, 必须主动扫描实现过程中是否有未纳入 spec 的问题, 有则补 task 并实现。
3. **禁止"遗留建议"模式**: 不得在最终总结中使用"遗留优化建议供后续参考"/"超出 spec 范围"/"如需实现请告知"等表述。这些表述 = 任务未完成。
4. **优化建议分级**: 发现的优化建议若确实超出当前 spec 范围 (如需引入新依赖/新架构), 必须在 spec 文档的"已知限制"段显式记录, 包含: 描述 + 影响范围 + 建议优先级 + 为何不本次实现。不得仅在对话中口头提及。

### 完成前必跑: 任务归属复查清单

```text
□ 1. 实现过程中是否发现新问题 / 优化点? → 有则立即纳入 spec (新增 task 或扩展现有 task)
□ 2. spec 阶段全部 ✅ 后, 是否主动扫描实现过程中的"假设"/"简化"/"临时方案"? → 有则补 task
□ 3. 测试失败修复后, 是否检查根因 (而非只改测试断言)? → 根因是代码问题则补 task 修代码
□ 4. 最终总结是否包含"遗留建议"/"超出 spec 范围"/"如需实现请告知"? → 有则违反本约束, 改为纳入 spec 并实现
□ 5. spec 文档是否有"已知限制"段? → 超出范围的优化必须记录在此段, 不得仅在对话中提及
□ 6. 自问: "我是否把本应本次做的事抛给了用户?" → 是则违反本约束, 立即纳入 spec 并实现
```

### 失败模式（禁止）

- ❌ spec 全部 ✅ + 测试通过 → 宣布任务完成, 把发现的优化作为"遗留建议"抛出 → ✅ 纳入 spec 并实现
- ❌ 测试失败只改断言, 不查根因 (如 Mock coord_transformer 问题) → ✅ 查根因, 代码问题则补 task 修代码
- ❌ 实现过程中发现 schema 不一致 / 测试缺口, 仅口头提及 → ✅ 立即新增 task 并实现
- ❌ 最终总结包含"遗留优化建议"/"超出 spec 范围"/"如需实现请告知" → ✅ 纳入 spec 并实现, 或在 spec "已知限制"段显式记录
- ❌ "抛锅"模式: 把本应本次做的事抛给用户二次确认 → ✅ 自动纳入 spec 并实现
- ❌ 检查清单只写在脑里 / 只写在 PR 描述 → ✅ 已迁出至 env-hardrules-contextual.md (由 orchestrator 触发加载, 非 L0 常驻)

### 触发条件 (任一即触发)

- 任何 `task_type=fix/add/refactor` 类任务的实现过程中发现新问题 / 优化点
- spec 阶段全部 ✅ 后, AI 准备宣布任务完成时
- 测试失败修复后 (检查根因是否是代码问题)
- 最终总结准备写"遗留建议"时

### 详细检查清单位置

- L1 索引: `meta/failure-modes.md` N193 行
- 触发本约束的任务: 在 `gaf-orchestrator` 决策树 step_1 标记 `task_type=fix/add/refactor` 时, 主动加载本段
- 与 N192 关系: N192 关注「报错可调试」, N193 关注「任务归属」, 二者互补不替代

## 测试数据硬约束 (N196)

> **状态**: 活跃 — 由 orchestrator 触发加载，非 L0 常驻

> 触发场景: **写测试时需要创建大文件 / 大数据量** (文件大小 > 10MB 或数据量 > 1000 行)。
> 根因: `test_cleanup_screenshots.py` 写真实 3-6GB 文件到磁盘 (3 个测试共写 37GB), 导致单次 backend 测试耗时 525s. 应 mock `Path.stat` / `os.stat` 返回 fake size, 只写 1 字节占位文件.

### 核心约束

1. **禁止在测试中写真实大文件** (> 10MB): 用 1 字节占位文件 + mock `Path.stat` / `os.stat` 返回 fake size
2. **禁止在测试中 `time.sleep`**: 用 `mock.patch('time.time')` 或 `freezegun` 模拟时间, 不真睡
3. **禁止在测试中发起真实网络请求**: 用 `responses` / `httpx_mock` / `mock.patch` 拦截
4. **测试数据量 > 1000 行时用工厂函数**: 不要硬编码 1000 行 fixture, 用 `[_make_row(i) for i in range(1000)]`

### 失败模式（禁止）

- ❌ `fpath.write_bytes(b'x' * (3 * 1024 ** 3))` 写真实 3GB 文件 → ✅ 写 1 字节 + mock `Path.stat` 返回 fake size
- ❌ `time.sleep(5)` 真睡 5 秒 → ✅ `mock.patch('time.time')` 模拟时间流逝
- ❌ 真实 `requests.get('http://...')` → ✅ `responses.add(responses.GET, url, body=...)`

## 诊断触发硬约束 (N204)

> **状态**: 活跃 — **L0 强制常驻提醒**（每次对话注入，见 env-hardrules.md §L0 强制常驻提醒）+ 详细清单按需 Read

> 触发场景: **对话中出现任务失败关键词或检测到 pipeline 节点执行异常时**。
> 根因: `pipeline-task-diagnosis` 技能只在 gaf-orchestrator bug_fix 分支条件引用, 规则层无 L0 硬约束强制 AI 在任务失败时自动加载诊断。导致 AI 可以合法跳过诊断直接改代码, 或只重启服务不定位根因。

### 核心约束

1. **对话中出现失败关键词时必须加载诊断**:
   - 关键词: "失败" / "超时" / "报错" / "识别不到" / "没反应" / "没变化" / "卡住" / "error" / "timeout"
   - 必须调用 `Skill(name='pipeline-task-diagnosis')` 获取诊断方法论
   - 即使任务被分类为 `new_feature` / `refactor` / `documentation` 也适用

2. **日志中出现 pipeline 错误码时必须加载诊断**:
   - 错误码: `NODE_TIMEOUT` / `TEMPLATE_NOT_FOUND` / `OCR_LOW_CONFIDENCE`
   - 从 `run.log` / `agent.log` / `execution.jsonl` 检测

3. **AI 不得跳过诊断**:
   - 除非明确确认不是 pipeline 节点问题 (如网络断开 / 数据库异常 / 前端构建错误)
   - 跳过诊断时必须记录理由

### 完成前必跑: 诊断触发检查清单

```text
□ 1. 对话中是否出现失败关键词? → 是则加载 pipeline-task-diagnosis
□ 2. 日志中是否出现 pipeline 错误码? → 是则加载 pipeline-task-diagnosis
□ 3. 是否跳过了诊断? → 必须记录理由 (确认非 pipeline 节点问题)
□ 4. 诊断后是否定位到具体失败节点? → 能则进入修复; 不能则继续隔离/验输入/弹窗/降级
```

### 失败模式（禁止）

- ❌ 用户说"节点失败了" → AI 直接改代码 → ✅ 先加载诊断 → 排除配置/数据流/弹窗问题
- ❌ 日志含 `NODE_TIMEOUT` → AI 只重启服务 → ✅ 先加载诊断 → 定位具体失败节点
- ❌ 上一节点成功但当前节点失败 → AI 直接重试 → ✅ 先检查弹窗遮挡 (高频失败场景)

### 详细检查清单位置

- L1 索引: `meta/failure-modes.md` N204 行
- 触发本约束的任务: 对话中检测到任务失败关键词 / 日志中出现 pipeline 错误码时

## 环境归一化 (N199, 已退役)

> **状态**: 退役 — 仅历史追溯 — 由 orchestrator 触发加载，非 L0 常驻

> 2026-08-02 归一化: 所有服务统一使用 `conda gaf` 环境，取消 `venv gaf-agent` 双环境设计。
> 根因: 原双环境设计基于 opencv 差异（backend headless vs agent full GUI），但实际 agent 代码未使用任何 GUI 函数（imshow/waitKey 等），`opencv-python-headless` 完全满足需求。双环境导致 agent 启动入口不统一，多次出现多进程冲突。

- **所有服务（backend + agent + 脚本）统一使用 conda gaf env**
- conda 环境路径: `D:\code\environment\conda\envs\gaf\python.exe`
- Python 版本: 3.11.15
- 启动方式: `scripts/gaf_services.ps1 start`（一键启动全部）
- 禁止手动 `python -m src` 启动 agent，必须通过 `gaf_services.ps1` 管理
- 代理端依赖统一在 `worker/requirements.txt` 中维护，安装到 conda gaf 环境
- 旧 venv 目录 `D:\code\environment\venvs\gaf-agent` 已废弃，不再使用

## 测试运行硬约束 (N194, 已退役)

> **状态**: 退役 — 仅历史追溯 — 由 orchestrator 触发加载，非 L0 常驻

> 触发场景: **任何跑 pytest 命令** (agent/backend/scripts 全量或单测, 验收 / 调试 / 回归任意目的)。
> 根因: `pyproject.toml` 配置 `DJANGO_SETTINGS_MODULE = "config.settings.dev"` + `pythonpath = ["backend"]`, pytest-django 插件检测到此配置后, 在 **每个测试 session** 都强制 `django.setup()` (加载 settings + apps + channels Redis 连接)。agent 测试根本不依赖 Django, 但 pytest-django 仍强制加载, 导致: (a) 单测试 12s 起步 (channels Redis 连接超时); (b) 全量 agent 测试 ~2h; (c) PowerShell 调 `conda run` 还会序列化 stdout 为 CLIXML 流, 进度完全看不到。AI 历史上多次跑 agent 测试都用默认命令 `python -m pytest worker/tests/`, 慢但未深究根因, 误判为 retry 真睡 / Windows IO 慢。

### 核心约束

1. **跑 agent 测试必用 `-p no:django -o addopts=""`** 禁用 pytest-django 插件:
   ```powershell
   # ✅ 正确 (2.5 分钟, 2154 passed)
   D:\code\environment\conda\envs\gaf\python.exe -m pytest worker/tests/ -p no:django -o addopts=""
   ```
2. **跑 backend 测试保持默认** (需要 Django):
   ```powershell
   D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/
   ```
3. **直调 `D:\code\environment\conda\envs\gaf\python.exe`** 而非 `conda run -n gaf python`, 避免 PowerShell 把 stdout 序列化成 CLIXML 流导致进度看不到
4. **测试慢时先用 `--durations=20` 定位最慢测试**, 再用 `python _time_xxx.py` 直跑对比, 区分 pytest 环境开销 vs 代码本身慢

### 触发条件 (任一即触发)

- AI 跑 `pytest worker/tests/` 或 `pytest worker/tests/test_xxx.py` 命令
- AI 跑 `pytest scripts/tests/` (脚本测试, 同样不依赖 Django)
- 用户反馈"测试慢" / "测试卡住" / "测试没结果"

### 失败模式（禁止）

- ❌ `conda run -n gaf python -m pytest worker/tests/` (默认配置, pytest-django 强制加载 Django, ~2h) → ✅ 加 `-p no:django -o addopts=""` (2.5min)
- ❌ `python -m pytest worker/tests/test_xxx.py` (单测也 12s) → ✅ 加 `-p no:django -o addopts=""` (0.02s)
- ❌ `conda run -n gaf python -m pytest ... | Tee-Object log.txt` (CLIXML 序列化, 进度看不到) → ✅ 直调 `D:\code\environment\conda\envs\gaf\python.exe`
- ❌ 测试慢就归因"代码本身慢" / "retry 真睡" / "Windows IO 慢", 不做对比实验 → ✅ 用 `--durations=20` + `python _time_xxx.py` 直跑对比, 区分 pytest 环境开销 vs 代码本身慢
- ❌ 长时间后台跑测试不检查 CPU 占用 → ✅ `Get-Process python | Select CPU, WorkingSet` 看 CPU 占用, CPU < 1% 说明在 sleep/IO 等待, 不是 CPU 计算

### 校验命令

```powershell
# 验证当前 pytest 配置是否含 DJANGO_SETTINGS_MODULE
Get-Content pyproject.toml | Select-String "DJANGO_SETTINGS_MODULE"

# 单测试对比验证 (加 -p no:django 应快 600x)
D:\code\environment\conda\envs\gaf\python.exe -m pytest "worker/tests/test_retry.py::TestRetryExhaustion::test_exhausts_and_reraises" --durations=5 --no-header
# 默认: 12.44s call
D:\code\environment\conda\envs\gaf\python.exe -m pytest "worker/tests/test_retry.py::TestRetryExhaustion::test_exhausts_and_reraises" --durations=5 --no-header -p no:django -o addopts=""
# 禁用 django: 0.02s call
```

### 详细检查清单位置

- 完整根因分析 + 实测对比: `../../.ai-memory/_archive/lessons-retired/N194-pytest-django-slowdown-agent-tests.md`
- L1 索引: `meta/failure-modes.md` N194 行
- 触发本约束的任务: 任何跑 pytest 命令前, 主动检查是 agent / backend / scripts 哪类测试, agent/scripts 类必加 `-p no:django -o addopts=""`
- 与 N188 关系: N188 约束 Python 环境 (conda gaf), N194 约束 pytest 配置 (禁用 django 插件), 二者互补

## URL 拼接归一化硬约束 (N197, 已退役)

> **状态**: 退役 — 仅历史追溯 — 由 orchestrator 触发加载，非 L0 常驻

> 触发场景: **任何涉及 URL 路径修改的任务** (新增 API 端点 / 修改路由 / 重构 API 版本号 / 跨层路径变更)。
> 根因: `backend/app_info.py` 的 `API_PREFIX` 只覆盖后端路由, agent 端和前端仍硬编码 `"/api/v2"`; app 路由路径段 (`accounts/`, `agents/` 等) 在 `config/urls.py` 中无统一映射。AI 修端口归一化时没扫 URL 路径段和版本号。

### 核心约束

1. **所有 API 版本号必须从 `GAF_API_PREFIX` 环境变量读取**, 禁止硬编码 `/api/v2/` 字符串
2. **所有 app 路由路径段必须从 `APP_ROUTES` 映射读取**, 禁止硬编码 `accounts/`、`agents/` 等路径段
3. **所有 Agent WebSocket 路径必须从 `GAF_WS_AGENT_PATH` 读取**, 禁止硬编码 `ws/protocol/agents/`
4. **后端 `config/urls.py` 必须使用 `APP_ROUTES` 映射拼路径**, 禁止直接写字符串
5. **前端 API 路径前缀必须从 `VITE_API_PREFIX` 构建时环境变量读取**, 禁止硬编码 `'/api/v2'`

### 覆盖范围 (必须检查的 4 层)

```text
□ backend 层: config/urls.py → 用 APP_ROUTES 拼接; config/settings/base.py → OAuth redirect URI 用 APP_ROUTES; routing.py → WS 路径用 WS_AGENT_PATH; middleware.py → WS 路径检查用 WS_AGENT_PATH
□ agent 层: config.py → 默认 server_url 从 GAF_WS_AGENT_PATH 推导; recording_api.py / step_recorder.py → api_prefix 从 GAF_API_PREFIX 读取; llm_client.py → DEFAULT_CHAT_PATH 从 GAF_API_PREFIX 读取
□ frontend 层: config/app.ts → API_PREFIX 从 import.meta.env.VITE_API_PREFIX 读取; frontend/.env → 设置 VITE_API_PREFIX
□ scripts 层: gaf_services.ps1 → WS 路径从 .env 读取; E2E 脚本 → 前端 URL 从 FRONTEND_URL 读取, API 路径从 GAF_API_PREFIX 读取
```

### 触发条件 (任一即触发)

- 任务涉及: 新增 API 端点 / 修改路由配置 / 重构 API 版本号 (如 v2 → v3)
- 任务涉及: 跨层 URL 路径修改 (backend 路由 + agent 请求 + 前端 API 调用)
- 任务涉及: 新增或修改 WebSocket 通道路径
- 任何涉及 `config/urls.py` 或 `config/app_info.py` 的修改

### 完成前必跑: URL 拼接归一化检查清单

```text
□ 1. 版本号检查: 所有层是否从 GAF_API_PREFIX 读取? grep 检查 agent/ frontend/ scripts/ 中的硬编码 /api/v2/
□ 2. 路由路径段检查: config/urls.py 是否使用 APP_ROUTES? 新增路由是否也用 APP_ROUTES 拼接?
□ 3. WebSocket 路径检查: routing.py 是否用 WS_AGENT_PATH? middleware.py 路径检查是否一致? agent 端默认 server_url 是否从 GAF_WS_AGENT_PATH 推导?
□ 4. 前端 API 前缀检查: config/app.ts 是否从 VITE_API_PREFIX 读取? frontend/.env 是否设置了 VITE_API_PREFIX?
□ 5. OAuth redirect URI 检查: settings/base.py 的 redirect URI 是否用 APP_ROUTES 拼接?
□ 6. 脚本/测试检查: E2E 测试脚本是否从 FRONTEND_URL / GAF_API_PREFIX 读取? 启动脚本的 WS 路径是否从环境变量读取?
□ 7. 自问: "如果明天改 API_PREFIX 从 api/v2 到 api/v3, 需要改几处?" → 答案应为 1 处 (.env 的 GAF_API_PREFIX)
□ 8. 自问: "如果明天改 agents 路由路径为 agent-instances, 需要改几处?" → 答案应为 1 处 (.env 的 GAF_ROUTE_AGENTS)
```

### 失败模式（禁止）

- ❌ 只在后端改 `API_PREFIX`, agent 端和前端仍硬编码 `/api/v2/` → ✅ 全部从 `GAF_API_PREFIX` 环境变量读取
- ❌ 在 `config/urls.py` 直接写路径字符串 `"accounts/"` → ✅ 用 `APP_ROUTES['accounts']` 拼接
- ❌ 在 `routing.py` 硬编码 `r"ws/protocol/agents/$"` → ✅ 用 `WS_AGENT_PATH` 变量
- ❌ agent 端 `f"{http_base}/api/v2"` 硬编码版本号 → ✅ 用 `os.environ.get("GAF_API_PREFIX", "api/v2")`
- ❌ 前端 `API_PREFIX = '/api/v2'` 硬编码 → ✅ 用 `import.meta.env.VITE_API_PREFIX || '/api/v2'`
- ❌ 启动脚本 `"ws://127.0.0.1:8000/ws/protocol/agents/"` 硬编码路径段 → ✅ 从 `GAF_WS_AGENT_PATH` 读取

### 详细检查清单位置

- 本约束触发条件: 任何涉及 URL 路径修改的任务, 主动加载本段
- 与 N191 关系: N191 关注 schema 数据流契约, N197 关注 URL 路径拼接, 二者互补

## 调度协调硬约束 (N198, 已退役)

> **状态**: 退役 — 仅历史追溯 — 由 orchestrator 触发加载，非 L0 常驻

> 触发场景: **任何启动服务 / 跑 pipeline / 任务调度 / 系统卡住排查** 场景。
> 根因: 调度协调机制在架构层面从未被设计, 架构文档只画了正常数据流, 缺异常控制流。AI 多次因 Celery Worker 未启动 / 进程重复 / Pending 无自动恢复 导致系统卡住。
> 相关文档: [dispatch-flow.md](../docs/architecture/cross-cutting/dispatch-flow.md) — 调度链路全貌 + 异常恢复机制。

### 核心约束

1. **服务启动顺序固定**: Redis → Backend (daphne) → Celery Worker → Celery Beat → Agent → Frontend
2. **每个服务只能有一个实例**: 启动前必须 `Stop-GafService` 杀旧实例, 启动后验证唯一性
3. **Pending 执行自动恢复**: Celery Beat 必须运行 `retry_pending_executions` (60s 周期), 扫描 PENDING 超 5 分钟的执行重试
4. **monitor 必须自动启动**: `gaf_services.ps1 start` 末尾自动启动 monitor 后台进程 (30s 检查周期)

### 完成前必跑: 调度协调检查清单

```text
□ 1. 服务启动顺序: 是否按 Redis → Backend → Worker → Beat → Agent → Frontend 顺序启动?
□ 2. 进程唯一性: 启动前是否杀旧实例? 启动后是否验证无重复进程?
□ 3. Celery Beat 运行: `retry-pending-executions` 任务是否在 beat_schedule 中注册?
□ 4. monitor 运行: 是否有后台 monitor 进程监控服务状态?
□ 5. 架构文档: 调度链路变更后是否更新 `dispatch-flow.md`?
□ 6. 自问: "如果某个服务挂了, 系统能自动恢复吗?" → 不能则补 monitor 或 beat 任务
```

### 失败模式（禁止）

- ❌ 跳过 `gaf_services.ps1` 手动启动单个服务 → ✅ 统一用 `gaf_services.ps1 start`
- ❌ 只启动 Worker 不启动 Beat (Pending 无自动恢复) → ✅ Worker + Beat 都启动
- ❌ 启动时手动杀进程 (PID 可能变化) → ✅ 用 `Stop-GafService` 按命令行匹配杀
- ❌ Celery 队列堆积不排查 (Worker 未注册) → ✅ 检查 `Redis SMEMBERS celery.worker-online`
- ❌ 系统卡住不按排查指南检查服务状态 → ✅ 先跑 `gaf_services.ps1 status` 看所有服务
