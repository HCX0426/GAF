---
summary: 小主题合并 Y/N 矩阵 — concurrency + browser-automation + control-message-routing + platform-env (spec-14 合并 + platform-env 迁入)
applies_to: [sync-lock, native-handle, singleton, playwright, browser-use, frontend-path, websocket, routing, agent-channels, reflection, dev-server-terminal, adb-storm, black-screen, autoreload]
last_updated: 2026-07-18
source: Merge of _concurrency.md + _browser-automation.md + _control-message-routing.md (spec-14) + platform-env N154/N155 cross-topic migration
---

# _misc.md — 小主题合并文件 (spec-14 合并; platform-env 迁入)

> **合并来源**: 4 个 ≤ 2 主要 N## 的小 sub-file 合并到此, 减少 yn-matrices/ file count (10 → 7; spec-14 3→1 后 8, spec-17 _hook-failure 合并后 7; N155 cross-topic 迁入后仍 7)
> **原文件**: `_concurrency.md` (131 行, N116+N146) + `_browser-automation.md` (38 行, N131) + `_control-message-routing.md` (94 行, N148)
> **迁入**: N154/N155 platform-env Y/N 矩阵从 `_ai-autonomy.md §㉖` 迁入, 修正 N155 lesson topic (platform-env) 与 Y/N 矩阵 topic (原 ai-autonomy) 不一致的历史遗留
> **保留原 §编号**: §5 concurrency / §8 browser-automation / §10 control-message-routing / §12 platform-env (方便交叉引用)

---

## §5 concurrency — 并发状态管理

### ⑯ N116 M1.G 协作冲突 + 性能分层 Y/N 矩阵 (R26 闭环 — N116 强化加项)

> **触发条件** (任意一条即触发):
> - 写 / 改 `scripts/bootstrap/sync_ai_memory.py` `update_sync_state()` R-M-W 逻辑
> - 写 / 改 `scripts/sync_*.py` 任何状态文件 (sync-state-2.json / bypass_audit.log / promote.log 等)
> - 改 `sync_ai_memory.py` 性能相关代码 (parse / query / index / regenerate)
> - 跨进程同时跑 `python scripts/bootstrap/sync_ai_memory.py` 场景
> - 1000 文件仓库 sync 跑 > 30s 反馈

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | `update_sync_state()` 整个 R-M-W 周期在 `_acquire_state_lock(timeout=5.0)` 内 | | `grep "_acquire_state_lock" scripts/bootstrap/sync_ai_memory.py` |
| 2 | `SyncLock` 上下文管理器跨平台 (fcntl POSIX + msvcrt Windows) | | `grep "_UnixBackend\|_WindowsBackend" scripts/sync_lock.py` |
| 3 | lockfile 路径用 `Path(".ai-memory/.sync.lock")` 常量, 不 inline 拼 | | `grep "SYNC_LOCK\|_lock_path" scripts/sync_lock.py` |
| 4 | `.gitignore` 排除 `.ai-memory/.sync.lock` (锁文件不进版本控制) | | `grep "\.sync\.lock" .gitignore` |
| 5 | `LockTimeout` 异常必须有 clear remediation (含竞争方 PID / 等待时间) | | `grep "class LockTimeout" scripts/sync_lock.py` |
| 6 | 改 `sync_ai_memory.py` 后必跑 `python scripts/layer_benchmark.py --stress 1000` 验证 | | 终端输出 4 tier 实测 |
| 7 | TARGETS 与 spec/tasks.md §2.7 同步 (L1<1s, L2<5s, stress_1000 ≤ 15s) | | `grep "TARGETS\s*=" scripts/layer_benchmark.py` |
| 8 | 6 锁测试 + 11 性能测试全过 | | `pytest scripts/tests/test_sync_lock.py scripts/tests/test_layer_benchmark.py` |

**AI 必做 (M1.G 协作冲突 + 性能分层硬规则)**:
- ✅ **任何 R-M-W 模式 (read-modify-write) 必须用 SyncLock 包裹** (复用 `acquire_repo_lock`)
- ✅ **跨平台锁 = fcntl + msvcrt 双 backend, lazy import** (Windows 没 fcntl 不报错)
- ✅ **lockfile 必须 .gitignore 排除** (`.ai-memory/.sync.lock` 不进版本控制)
- ✅ **改 sync 流程必跑 layer_benchmark.py 验证** (防性能回归静默)
- ✅ **target 改必须 spec + code 同步** (N106 家族: `tasks.md` + `layer_benchmark.py: TARGETS` + `test_layer_benchmark.py: TargetTests`)
- ✅ **Windows NTFS + AV + Python startup 是固定开销** (~0.4s/subprocess), target 必须留 buffer
- ❌ **NEVER 改 update_sync_state 而不加锁** (N100 家族隐性 bug)
- ❌ **NEVER 用 try/except 吞 LockTimeout** (用户需要看到, 不需要 fallback)
- ❌ **NEVER 拍脑袋设 10s 1000 文件** (实测 Windows 11.89s, 必须跑过 1000 文件再定目标)
- ❌ **NEVER 改 sync 流程而不跑 benchmark** (性能回归静默)
- ❌ **NEVER inline 拼路径** (用 `SYNC_STATE` / `SYNC_LOCK` 常量, 符合 N106 家族)

**实测基线** (Windows 11 NTFS, 22 lessons 仓库):
| 层级 | 实测 | 目标 | 余量 |
|------|-----:|-----:|-----:|
| L1_query | 0.25s | ≤ 1.0s | 75% |
| L1_stats | 0.41s | ≤ 1.0s | 59% |
| L2_full_sync (median 3) | 0.40s | ≤ 5.0s | 92% |
| stress_1000 | 5.32s (热) / 11.89s (冷) | ≤ 15.0s | 21% |

**同根因家族**: N82 (审计) + N100 (文件损坏) + N101 (状态不诚实) + N106 (路径漂移) + **N116 (本条 并发状态管理缺位)** —— 同根因 (并发状态管理缺位)

---

### ㉕ N146 ctypes.CDLL 热循环必须模块级单例缓存 Y/N 矩阵 (TD-011 闭环)

> **触发条件** (任意一条即触发):
> - 写 / 改截图/输入/轮询等热循环（每秒/每帧调用）代码
> - 在循环内 `ctypes.CDLL(path)` / `CoCreateInstance` / `subprocess.Popen` 构造 native 句柄对象
> - agent 出现 `0xC0000005` (ACCESS_VIOLATION) exit code -1073740771 崩溃
> - 日志中 `*.dll loaded` / `*.dll unloaded` 每秒重复出现
> - 涉及 IScreenShotClass / vtable / 函数指针的 native 调用

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 热循环（每秒/每帧调用）内是否构造 `ctypes.CDLL(path)` 实例？ | Y=有风险 | `grep -rn "ctypes.CDLL" worker/src/` 看是否在循环路径 |
| 2 | 热循环内是否 `new` 包含 native 句柄的对象（CDLL/COM/Win32 handle）？ | Y=有风险 | 看构造函数是否调 `LoadLibrary`/`CoCreateInstance`/`CreateFile` |
| 3 | native 对象方法是否访问 vtable/函数指针？ | Y=有风险 | vtable 指针在 DLL unload 后失效 → ACCESS_VIOLATION |
| 4 | 是否有 `LoadLibrary`/`dlopen` 在循环内重复调用？ | Y=有风险 | 必须移到模块级单例初始化 |
| 5 | 单例工厂是否使用双重检查锁（外层无锁 + 内层 `threading.Lock`）？ | N=线程不安全 | 并行截图（ThreadPoolExecutor）下多线程首次调用会重复创建 |
| 6 | 回归测试是否验证 state（如 api_version）在多次调用后稳定？ | N=缺失 | `pytest tests/test_ldopengl.py::TestLDOpenGLSingleton` |
| 7 | 测试断言模块全局变量是否用 `import module as mod` + `mod.GLOBAL`？ | N=值快照陷阱 | `from module import GLOBAL` 在 import 时为 None，后续不更新 |

**AI 必做 (native 句柄热循环硬规则)**:
- ✅ **热循环内 native 句柄对象必须模块级单例缓存**: `ctypes.CDLL` / `CoCreateInstance` / `subprocess.Popen` 在每秒/每帧调用的代码路径内禁止直接构造
- ✅ **单例工厂必须双重检查锁**: 外层无锁快路径 + 内层 `threading.Lock` 防 A2 并行截图（max_workers=4）下并发首次创建
- ✅ **回归测试必须验证 state 稳定性**: `api_version` 在 N 次调用后不变，而非只验证"能调用"
- ✅ **`from module import GLOBAL_VAR` 创建值快照**: 测试断言模块全局变量必须 `import module as mod` + `mod.GLOBAL_VAR`
- ✅ **`if self._initialized: return` 实例级守卫不能替代模块级单例**: 新建实例本身就触发 LoadLibrary，守卫不跨实例生效
- ❌ NEVER 在截图/输入/轮询等热循环内 `new` 包含 native 句柄的对象
- ❌ NEVER 用实例级守卫替代模块级单例（新建实例本身就触发 LoadLibrary）
- ❌ NEVER 在测试中 `from module import GLOBAL_VAR` 后断言其值（import 时为 None，后续不更新）

**反模式代码示例**:
```python
# ❌ 反模式：每次截图创建新实例
@retry_screenshot()
def _capture_ldopengl(self):
    capture = LDOpenGLCapture()  # 每次 new → LoadLibrary
    return capture.capture()    # 返回后 capture GC → FreeLibrary

# ✅ 正确模式：模块级单例 + 双重检查锁
_LDOPENGL_LOCK = threading.Lock()
_LDOPENGL_CAPTURE_INSTANCE = None

def get_ldopengl_capture():
    global _LDOPENGL_CAPTURE_INSTANCE
    if _LDOPENGL_CAPTURE_INSTANCE is None:
        with _LDOPENGL_LOCK:
            if _LDOPENGL_CAPTURE_INSTANCE is None:
                _LDOPENGL_CAPTURE_INSTANCE = LDOpenGLCapture()
    return _LDOPENGL_CAPTURE_INSTANCE

@retry_screenshot()
def _capture_ldopengl(self):
    capture = get_ldopengl_capture()  # 单例，DLL 只加载一次
    return capture.capture()
```

**实测基线** (真实 LDPlayer dnplayer PID 7120):
| 指标 | 修复前 | 修复后 |
|------|-------:|-------:|
| "ldopengl64.dll v3 API loaded" 日志频率 | 每秒 1 次 | 进程生命周期 1 次 |
| agent 崩溃 (ACCESS_VIOLATION) | ~1-2 小时后 | 无 (5 张截图 + 单元测试 73/73 PASS) |
| api_version 稳定性 | 0 → 3 每次循环 | 稳定为 3 |

**同根因家族**: N141 (screenshot benchmark 盲区 — native 资源生命周期管理缺位) + N138 (ctypes HRESULT 有符号比较 — ctypes 使用陷阱) —— 同根因 (native/ctypes 资源生命周期管理缺位)

**关联**:
- `.ai-memory/lessons/N146-ldopengl-singleton-ctypes-hot-loop.md` (L1 已升级)
- `.ai-memory/summaries/architecture-mistakes.md` N146 条目
- `worker/src/platforms/windows/ldopengl.py` (`get_ldopengl_capture`, `_LDOPENGL_LOCK`, `_LDOPENGL_CAPTURE_INSTANCE`)
- `worker/src/devices/adb/device.py` (`_capture_ldopengl`)
- TD-011 (tech-debt/fixed.md ✅ FIXED), C-015 (completed-features.md)
- commit: `-` (代码) + `-` (文档)

---

## §8 browser-automation — Playwright/browser-use

### N131 Browser automation toolchain + frontend path mismatch (参考, 无独立 Y/N 矩阵)

> **注**: N131 是关于 Windows 环境下浏览器自动化工具链缺失 + 前端路径漂移的教训。
> N131 没有独立的 Y/N 矩阵格式, 完整内容在 lesson 文件中。
>
> **来源**: `GAF/.ai-memory/lessons/N131-playwright-browser-automation.md`
>
> **触发条件**:
> - AI 需要登录前端 / 读取 console 信息驱动改进
> - Windows 环境无 `bash.exe` / `browser-use` CLI / `playwright` / `selenium`
> - 前端 axios 路径与 Django URL mounting 不匹配 (404)
>
> **核心教训**:
> 1. **不要假设浏览器自动化可用**: Windows 上 `bash` 和 `browser-use` 可能缺失; 在项目 dev deps 中声明 Playwright 以保证工具链可复现
> 2. **Console-reading smoke test 捕获路径漂移**: setup endpoint 上的 404 不阻塞登录 (页面 fallback 到 `registerEnabled=true`), 但在真实浏览器中会暴露
> 3. **前端 axios 路径必须匹配 Django URL mounting**: endpoint 挂载在 `accounts.urls` 下时, 前端必须请求 `/accounts/<endpoint>/`, 不能请求 `/<endpoint>/`
>
> **修复步骤**:
> 1. 在 `pyproject.toml` dev dependencies 中加 `playwright>=1.40,<2.0`
> 2. 跑 `python -m playwright install chromium` (下载 ~300 MB 到 `%LOCALAPPDATA%\ms-playwright`)
> 3. 用 Playwright sync API 填 `input[autocomplete="username"]`, `input[autocomplete="current-password"]`, 点击 `button[type="submit"]`, 等待 URL **/dashboard, 捕获 console errors / page exceptions
> 4. 修前端路径: `client.get('/init/status/')` → `client.get('/accounts/init/status/')` (global axios client baseURL 是 `/api/v2/`, Django endpoint 挂载在 `accounts.urls`)
> 5. 把场景接入 `scripts/e2e/run_all.py` 作为 `browser_login`, 加到 `scripts/e2e/conftest.py::SCENARIO_NAMES`
>
> **同根因家族**: N118 (test environment assumptions) + N122 (scripts maintenance) + **N131 (本条)** —— 同根因 (测试/工具链缺位)

---

## §10 control-message-routing — 双向控制消息路由 (N148)

> **来源**: `gaf-lesson-router/SKILL.md` N148 + `architecture-mistakes.md` N148 摘要
> **触发场景**: 写任何 frontend → backend → agent 的双向控制消息（start/stop, request/cancel, subscribe/unsubscribe）时

### N148 Y/N 矩阵 (㉙)

**写双向控制消息时必跑 (5 项)**:
- [ ] **Y**: 上行消息（start/request/subscribe）和下行消息（stop/unsubscribe/cancel）**都**包含 `agent_id` 路由字段？
  - 反例: useScreenshotStream.stopStream() 发 `{}` payload 缺 agent_id → backend 静默丢弃 → agent 持续推帧
  - 正例: stopStream 用 useRef 保留 agent_id, stop 时显式放进 payload
- [ ] **Y**: hook 的 stop/unsubscribe API 即使无参数，也通过 `useRef` / state 保留路由标识？
  - 反例: `const stopStream = useCallback(() => wsClient.send('stop', {}), [])`
  - 正例: `const stopStream = useCallback(() => { wsClient.send('stop', { agent_id: ref.current }); ref.current = null; }, [])`
- [ ] **N**: 后端守卫用 `and agent_id` 静默丢弃空值？
  - 反例: `elif msg_type == "stop_xxx" and agent_id:` (空 agent_id 时无日志无 error frame, bug 不可观测)
  - 正例: `elif msg_type == "stop_xxx":` 后 + `if not agent_id: logger.warning("..."); return`
- [ ] **Y**: serializer 显式暴露业务标识符字段（如 `agent_identifier`）给前端？
  - 反例: 只暴露 FK 字段 `agent` (DB pk int), 前端被迫猜测哪个是路由标识
  - 正例: `agent_identifier = SerializerMethodField(read_only=True)` 返回业务 string
- [ ] **N**: 前端用 `record.agent` (DB pk) 做路由？
  - 反例: `setMonitoringAgentId(record.agent ? String(record.agent) : undefined)` 路由到 `agent_4` 不存在的 group
  - 正例: `setMonitoringAgentId(record.agent_identifier ?? undefined)`

### 通用模式: 显式区分 FK pk 和业务标识符

```python
# ❌ 反模式: 序列化层不区分, 前端被迫猜测
class TaskExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ['agent', ...]  # 'agent' 是 FK pk (int 4), 不是路由标识

# ✅ 正确: 显式暴露业务标识符字段
class TaskExecutionSerializer(serializers.ModelSerializer):
    agent_identifier = serializers.SerializerMethodField(read_only=True)

    def get_agent_identifier(self, obj):
        return obj.agent.agent_id  # 业务 string (e.g. "td010-repro-agent")

    class Meta:
        fields = ['agent', 'agent_identifier', ...]
```

### 通用模式: 双向 hook API 用 ref 保留状态

```typescript
// ❌ 反模式: stop 无参数, 后端不知道路由给谁
const stopStream = useCallback(() => {
  wsClient.send('stop_screenshot_stream', {});
  setIsStreaming(false);
}, []);

// ✅ 正确: ref 保留 agent_id, stop 时主动传递
const activeAgentIdRef = useRef<string | null>(null);
const startStream = useCallback((agentId: string) => {
  activeAgentIdRef.current = agentId;
  wsClient.send('request_screenshot_stream', { agent_id: agentId });
  setIsStreaming(true);
}, []);
const stopStream = useCallback(() => {
  const agentId = activeAgentIdRef.current;
  wsClient.send('stop_screenshot_stream', { agent_id: agentId });
  activeAgentIdRef.current = null;
  setIsStreaming(false);
}, []);
```

**验证步骤**:
1. 在前端 stop 按钮处加 `console.log('stop payload', payload)` 检查 agent_id 存在
2. 在 backend consumer 加 `logger.info("[BACKEND] stop request: agent_id=%s", agent_id)` 检查收到
3. 在 agent handler 加 log 检查 stop 消息被处理
4. 端到端: 点击 stop 后 agent 应停止推帧, 日志显示 stream closed

**反模式列表** (遇到时立即修):
- ❌ 静默丢弃空路由标识 (无 error frame, 无 warning log)
- ❌ 把 FK pk (int) 当成路由 string 用
- ❌ stop API 无参数, 依赖隐式状态
- ❌ Channels group name 混用 string id 和 DB pk

**关联**:
- `.ai-memory/lessons/N148-control-message-routing-and-db-pk-vs-business-id.md` (L1 已升级)
- `.ai-memory/summaries/architecture-mistakes.md` N148 段
- 修复 commit: `-` (stopStream + App.useApp)、`-` (agent_identifier)

---

## §12 platform-env — 平台环境问题 (N154/N155 黑屏家族)

> **迁入历史**: 本段原在 `_ai-autonomy.md §㉖` (N155 cross-topic 历史遗留 — N155 lesson 在 platform-env topic 但 Y/N 矩阵在 ai-autonomy topic)。修正此遗留, 将 N154 + N155 Y/N 矩阵合并迁入本段, 与 lesson topic (platform-env) 一致。
> **同根因家族**: N109 (决策自决) + N154 (黑屏代码层修复) + N155 (黑屏行为层修复) — 同根因 (AI 自决权 + 系统稳定性安全边界)

### ㉙ N154/N155 黑屏家族 Y/N 矩阵 (重定义 N155)

> **N154 (Active, 代码层修复)**: ADB subprocess storm + N146 backend gap → 黑屏 — 后台循环 >= 30s; 危险操作默认禁用 (opt-in); N146 单例修复必须覆盖 ALL 代码路径; ADB 优先用模拟器自带
> **N155 (Dormant, 行为层修复, 重定义)**: N155 原范围 "backend .py 修改触发 autoreload 需确认" 已被代码层修复 (`_kill_stale_agent_processes()` + `GAF_AUTO_START_AGENT=0` 默认) 消解, project_rules §3.5 明确 "backend .py 编辑不需要确认"。N155 现范围为 "重复启动 dev server 终端需检查" — 启动新 runserver/npm run dev/celery worker 终端前检查已有进程, 避免端口冲突 / agent 叠加 / 黑屏。

> **触发条件** (任意一条即触发):
> - AI 准备启动新的 dev server 终端 (runserver / npm run dev / celery worker / agent)
> - 用户原话 "启动后端" / "启动前端" / "重启 dev server" / "怎么防止这种黑屏问题"
> - N154 黑屏事件复发 (agent 叠加 → adb 风暴)

**Y/N 检查表 (N155 行为层)**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 本轮要启动新的 dev server 终端？ | | 列出终端类型 (runserver/npm run dev/celery worker/agent) |
| 2 | 已检查是否已有同类终端在运行？ | | `Get-Process | Where-Object {$_.ProcessName -match 'python\|node'}` 或 ps 看端口占用 |
| 3 | 已检查端口占用 (8000 backend / 5173 frontend)？ | | `Get-NetTCPConnection -LocalPort 8000,5173` |
| 4 | 若已有终端运行, 已告知用户并询问是否复用？ | | 文本输出含询问 |
| 5 | 启动前确认 GAF_AUTO_START_AGENT=0 (默认)？ | | `echo $env:GAF_AUTO_START_AGENT` |
| 6 | backend .py 编辑无需此检查 (代码防护已让 autoreload 安全)？ | | 见 project_rules §3.5 |

**AI 必做 (N154 代码层 + N155 行为层)**:
- ✅ **N154 代码层**: 后台循环 >= 30s; 危险操作默认禁用 (opt-in); N146 单例修复覆盖 ALL 代码路径; ADB 优先用模拟器自带
- ✅ **N155 行为层 启动新 dev server 终端前 3 步**: ① 检查同类终端是否已在运行 ② 检查端口占用 ③ 若已运行, 询问用户是否复用
- ✅ **backend .py 编辑不需要此检查**: 代码防护 (`_kill_stale_agent_processes()` + `GAF_AUTO_START_AGENT=0` 默认) 已让 autoreload 安全 (见 project_rules §3.5)
- ✅ **例外 (无需此检查)**: frontend / .md / 测试文件 / agent 目录 / .env 配置 — 不启动 dev server 终端
- ❌ **NEVER 已有 runserver 终端运行时再启动第二个 runserver** (端口冲突 + agent 叠加 → 黑屏, N155 核心反模式)
- ❌ **NEVER 认为 N109 自决权覆盖此场景** (系统稳定性安全边界, 需用户确认)
- ❌ **NEVER 启动新 dev server 时不检查端口占用** (8000/5173 占用 → 启动失败或叠加)

**N155 vs N154 区别**:
- N154: "ADB subprocess storm → 黑屏" — **代码层**修复 (后台循环 >= 30s + 默认禁用 + kill stale agent)
- **N155 (重定义)**: "重复启动 dev server 终端需检查" — **行为层**修复 (AI 启动前检查已有进程)
- N154 修代码, N155 修 AI 行为; 互补, N155 是 N154 同日复发的根因修复

**正向模板 (N155 推荐)**:
- "本轮需启动后端 dev server。先检查端口 8000 是否被占用 — `Get-NetTCPConnection -LocalPort 8000`。若已有 runserver 进程, 询问用户是否复用现有终端。确认 GAF_AUTO_START_AGENT=0 后启动。"
- 例外场景: "本轮只改 backend .py 文件, 无需启动新 dev server 终端 — autoreload 自动重载, 代码防护已让此操作安全 (见 project_rules §3.5)。"

**关联**:
- `.ai-memory/lessons/N154-n155-black-screen-agent-storm.md` (家族合并主条目, 含 N154 + N155 完整复发历史)
- `.ai-memory/summaries/architecture-mistakes.md` N154/N155 段
- `project_rules.md §3.5` (backend .py 编辑不需确认 — N155 代码层消解)
- 修复 commit: N154 代码层修复 + N155 cross-topic 迁移

### ㉛ N186/N187 agent 进程管理 + venv 依赖漂移 Y/N 矩阵 (2026-07-23 BD2 测试暴露)

> **N186 (Active, 代码层)**: agent 独立进程 (`worker/src/__main__.py`) 无 PID 文件锁, 手动 `python -m src` 启动会重复进程; 与 backend 端 `agent_runtime.py` (TD-217) 是两个独立东西, 互补不重叠
> **N187 (Active, 部署层)**: venv gaf-agent 与 conda gaf env 双环境隔离是官方设计 (opencv headless vs full), 但两环境都需要装的依赖 (rapidocr-onnxruntime) 必须在 agent/requirements.txt 与 backend/requirements/base.txt 同步; 懒加载掩盖缺失

**同根因家族**: N154/N155 (黑屏家族, backend 自启 agent 场景) + N186 (agent 自身单例锁) + N187 (venv 依赖漂移) — 同源 (agent 启动流程不完善), 但代码层根因不同

**Y/N 检查表 (N186 agent 单例锁)**:
| 触发场景 | Y/N | 动作 |
|---------|-----|------|
| 手动 `python -m src` 启动 agent | ✅ Y | `acquire_singleton_lock()` 写 PID 文件, 已有存活 PID 则 exit(1) |
| backend 自启 agent (GAF_AUTO_START_AGENT=1) | N | backend `agent_runtime.py` (TD-217) 已管, agent 自身锁不冲突 (standalone.pid vs agent.pid 不同文件) |
| agent 异常崩溃 (未释放锁) | ✅ Y | 下次启动检测 PID 不存活, 自动 reclaim stale lock |
| 调试场景需多 agent | ✅ Y | `--skip-singleton-check` 绕过 (仅限调试, 不推荐生产) |

**Y/N 检查表 (N187 venv 依赖漂移)**:
| 触发场景 | Y/N | 动作 |
|---------|-----|------|
| 新增 agent 端依赖 | ✅ Y | 同步加到 `agent/requirements.txt` + `backend/requirements/base.txt` (若 backend 也需要) |
| 新增 backend 端依赖 | ✅ Y | 仅加到 `backend/requirements/base.txt`; 若 agent 也需要 (如 OCR 引擎), 同步加到 `agent/requirements.txt` |
| 修改 opencv 版本 | ✅ Y | 两边各自维护 (backend headless, agent full), **不**强行对齐版本 |
| 新增 OCR/识别引擎依赖 | ✅ Y | 必须双环境同步 (agent 跑 pipeline 节点, backend 跑独立 API) |
| setup-dev-env.ps1 重装环境 | ✅ Y | 验证 `agent/requirements.txt` 与 `backend/requirements/base.txt` 交集依赖都装上 |

**AI 必做 (N186 + N187)**:
- ✅ **N186**: 手动启动 agent 前不检查已有进程 (代码层已兜底, 但仍建议检查避免 exit(1) 浪费); 调试多 agent 用 `--skip-singleton-check`
- ✅ **N187**: 修改 agent/requirements.txt 或 backend/requirements/base.txt 时, 检查交集依赖是否同步; 新增 OCR/识别类依赖必双环境都装
- ❌ **NEVER 假设 venv gaf-agent 有 conda gaf env 的所有依赖** (双环境隔离, 重复库是间接依赖, 但核心能力依赖如 rapidocr 必须显式声明)
- ❌ **NEVER 用懒加载掩盖核心依赖缺失** (OCR 是 agent 核心能力, 缺 rapidocr 应在启动期警告而非 pipeline 执行期才报错)

**N186 vs N154/N155 区别**:
- N154/N155: backend 自启 agent 场景 (代码层 `_kill_stale_agent_processes()` + 行为层"启动前检查")
- N186: agent 自身独立进程 (代码层 `acquire_singleton_lock()` PID 文件锁)
- N154 修 backend 端, N186 修 agent 端; 互补, N186 是 N154/N155 同源问题的 agent 端补丁

**关联文档**:
- `.ai-memory/lessons/N186-agent-standalone-process-no-pid-lock.md`
- `.ai-memory/lessons/N187-venv-deploy-dep-drift.md`
- `docs/tech-debt/active.md` TD-339 (agent 单例锁) + TD-337 (rapidocr 遗漏)
- `docs/architecture/overview.md` §10.3 (agent 进程管理两层机制)
- `docs/architecture/desktop/deployment-design.md` §2.4 (双环境依赖说明) + §4.3 (本地开发 token)
- 修复 commit: TD-337 (requirements.txt 补 rapidocr) + TD-339 (agent __main__.py PID 锁) + TD-340 (heartbeat 10s)

### ㉜ N211 窗口设备固定 title/hwnd 锚定失效 Y/N 矩阵 (2026-08-28 补登, agent-platform)

> **触发条件** (任意一条即触发):
> - 用固定 window title 或固定 hwnd 锚定浏览器/游戏窗口设备
> - 页面标题会变 / 浏览器重启后句柄失效导致设备绑定失败

**Y/N 检查表**:
| # | 检查项 | Y/N | 验证 |
|:-:|--------|:---:|------|
| 1 | 窗口设备执行时实时匹配 (子串标题 / 进程名), 而非固定 title 锚定? | | 匹配逻辑用 find_window 子串匹配 |
| 2 | hwnd 缓存失效时强制重连重绑 (而非沿用旧句柄)? | | 缓存命中校验 + 失效重绑路径 |
| 3 | 设备描述避免硬编码会变的 UI 文案 (页面标题会变)? | | title 取子串/识别名 |

**AI 必做 (N211 硬规则)**:
- ✅ 浏览器/游戏窗口设备靠实时匹配 (子串/进程名) 锚定, 不靠固定 title 或固定 hwnd
- ✅ hwnd 缓存过期/失效 → 强制重连重绑
- ❌ **NEVER 固定 title / 固定 hwnd 作为长期锚点** (页面标题会变, 句柄随浏览器重启变)

**实测基线 (N211 闭环)**:
- 触发: 2026-08-28 页面标题变化 + 浏览器重启后句柄失效
- lesson: `lessons/agent-platform_2026-08-28_n211-window-device-dynamic-binding.md`

**同根因家族**: N154/N155 (黑屏家族, 窗口/设备状态失效场景) + **N211 (本条 窗口动态绑定)** —— 同根因 (设备状态以静态假定, 缺动态重连机制)

---
