---
maintainer: manual
source: 用户反馈 "测试为啥这么久, 看慢的原因" (2026-07-29)
load_when: [pytest, agent-tests, slow-tests, test-timeout, pytest-django, DJANGO_SETTINGS_MODULE, test-hang, conda-run-clixml, markexpr, e2e-skip, addopts]
priority: high
symptom: [kb:pytest-django-slowdown, N194, L0-missing, test-hardrules, markexpr-not-honored]
solution: "agent 测试必用 -p no:django -o addopts=''; 禁用 conda run 包装层用直调 python.exe; PowerShell 跑 conda run 会序列化 CLIXML 导致 stdout 丢失; pyproject 的 markexpr 非标准 pytest 选项静默不生效, e2e 跳过用 addopts = ['-m', 'not e2e']"
diff_keywords: [pytest, addopts, markexpr, e2e-skip, pyproject]
related_files:
  - .trae/rules/env-hardrules.md
  - .ai-memory/meta/failure-modes.md
  - pyproject.toml
  - agent/conftest.py
  - agent/tests/conftest.py
created_by: AI
topic: testing
last_updated: 2026-08-16
---

# N194 — pytest-django 插件拖慢 agent 测试 (单测 12s → 0.02s)

## Problem（症状 / 触发条件）

2026-07-29 用户反馈: "跑一次 (agent 测试), 为啥测试会这么久"

### 现象
- agent 全量测试 85 文件 / 2157 用例, 预计 2 小时
- 实际跑 10 分钟才到 13% 进度, CPU 占用 < 1% (99% 时间在 sleep/IO 等待)
- 单个测试 `test_exhausts_and_reraises` 跑 12.44s, 但代码只有 `delay=0.01` (应 30ms)
- 直接 `python _time_retry.py` 跑同样代码只要 20ms, 差 620 倍

### 触发条件

AI 跑 agent 测试时用默认命令:
```powershell
# ❌ 慢命令 (2 小时)
conda run -n gaf python -m pytest agent/tests/
# 或
D:\code\environment\conda\envs\gaf\python.exe -m pytest agent/tests/
```

## Root Cause（根因链）

本次排查发现的根因链:

### 根因 #1 (主因): pytest-django 插件强制 Django setup

1. `pyproject.toml` L125-130 配置了:
   ```toml
   [tool.pytest.ini_options]
   DJANGO_SETTINGS_MODULE = "config.settings.dev"
   pythonpath = ["backend"]
   ```
2. pytest-django 插件检测到 `DJANGO_SETTINGS_MODULE` 配置后, 在 **每个测试 session** 都触发 `django.setup()` (加载 settings + apps + 数据库连接 + channels Redis 连接)
3. agent 测试根本不依赖 Django, 但因为 `pyproject.toml` 是全局配置, pytest-django 仍强制加载
4. 单测试 Django setup 开销 ~12 秒 (channels 模块尝试连 Redis 超时)
5. 85 个测试文件每个都付这个开销 (实际是 session 级, 但 `--durations` 显示在第一个测试的 setup 上, 后续测试也因 db transaction 回滚变慢)

### 根因 #2 (次因): PowerShell conda run 包装层序列化 stdout

1. PowerShell 调 `conda run -n gaf python ...` 会把子进程 stdout 序列化成 CLIXML 流
2. `Tee-Object` / `Out-File` 拿到的是 `<Objs Version="1.1.0.1" xmlns="...">` 序列化对象, 不是文本
3. 进度条完全看不到, 看起来像"卡住"
4. 额外 CPU 开销 + 反复 poll 检查加剧慢感

### 根因 #3 (误导): 误判为 retry 真睡

1. 日志显示大量 `retrying in 0.20s` / `retrying in 0.50s`
2. `agent/src/core/retry.py:289` 的 `_interruptible_sleep` 用真 `time.sleep`
3. 初步判断: retry 真睡是慢根因
4. **但**: 单测 `delay=0.01` 也跑 12 秒, 与 retry 无关
5. 用 `python _time_retry.py` 直跑只要 20ms, 证明 retry 代码本身不慢
6. 真根因是 pytest-django 插件, 不是 retry 代码

### 根因 #4 (2026-08-16 TD-363 追加): pyproject `markexpr` 非标准选项静默不生效

1. `pyproject.toml` 原配置 `markexpr = "not e2e"` 期望默认跳过 e2e 标记测试 (需要外部服务: 浏览器/前端)
2. 但 `markexpr` 不是 pytest 标准 ini 选项 (是第三方插件选项), pytest 每次运行都报 `PytestConfigWarning: Unknown config option: markexpr` 且**完全不生效**
3. 后果: 默认 `pytest scripts/tests/` 也执行 e2e 测试, 浏览器场景 `ERR_CONNECTION_REFUSED: 127.0.0.1:5173` 假失败混入全量回归 (TD-363 的 18 个预存失败之一)
4. 根因修复: 改 `addopts = ["-m", "not e2e"]` (pytest 标准方式, CLI `-m` 可覆盖 addopts), 默认跳过 e2e; `-o addopts=""` (N194 agent 测试命令) 会清空该默认, 需要 e2e 时显式 `-m e2e`
5. 验证: `pytest scripts/tests/` 全绿 = 562 passed + 31 deselected (e2e 正确跳过)

## Solution（修复方案）

### L0 硬约束 (env-hardrules.md)

见 `.trae/rules/env-hardrules.md` "测试运行硬约束 (N194 新增)" 段。

### 跑 agent 测试的正确命令

```powershell
# ✅ 快命令 (2.5 分钟, 2154 passed)
D:\code\environment\conda\envs\gaf\python.exe -m pytest agent/tests/ -p no:django -o addopts=""
```

关键参数:
- `-p no:django`: 禁用 pytest-django 插件, 跳过 Django setup
- `-o addopts=""`: 清空 pyproject.toml 里 addopts 的默认 flags (可能有 `-p no:cacheprovider` 等)
- 直调 `D:\code\environment\conda\envs\gaf\python.exe`: 绕过 conda run 包装层, 避免 CLIXML 序列化

### 跑 backend 测试的命令 (保持不变)

```powershell
# backend 测试需要 Django, 不禁用插件
D:\code\environment\conda\envs\gaf\python.exe -m pytest backend/
```

## Verification（验证）

2026-07-29 实测对比:

| 命令 | 单测试耗时 | 全量耗时 | 备注 |
|------|-----------|---------|------|
| `python -m pytest test_retry.py::test_exhausts_and_reraises` | 12.44s call | ~2h | 默认配置, pytest-django 加载 |
| `python -m pytest test_retry.py::test_exhausts_and_reraises -p no:django -o addopts=""` | 0.02s call | - | 禁用 django 插件 |
| `python _time_retry.py` (直跑) | 0.02s | - | 不经 pytest |
| `python -m pytest agent/tests/ -p no:django -o addopts=""` | - | **150s (2154 passed)** | 全量 agent 测试 |

速度提升: 单测试 620x, 全量 48x (2h → 2.5min)

## Reflection（反思 — N193 反思链）

### 为什么之前没发现?

1. **历史跑测试都用默认命令**: 之前 AI 跑 agent 测试都是 `conda run -n gaf python -m pytest agent/tests/`, 慢但不知道为什么
2. **CLIXML 问题掩盖了真相**: conda run 把 stdout 序列化, 进度看不到, AI 以为"测试本身慢"
3. **未做对比实验**: 没有用 `python _time_retry.py` 直跑对比, 也没用 `--durations=20` 看具体慢在哪
4. **误判根因**: 看到 retry 日志 `retrying in 0.20s` 就以为是 retry 真睡, 实际 retry 代码没问题

### 下次新对话还会犯吗?

**如果只沉淀到 L3 lesson (按需加载, AI 不主动读) — 会犯**

按 N193 任务归属硬约束, 必须升级到 L0:
- ✅ L0 `.trae/rules/env-hardrules.md` 加 "测试运行硬约束" 段 (每次对话强制加载)
- ✅ L1 `failure-modes.md` 加 N194 索引 (gaf_init.sh 启动硬加载)
- ✅ L3 本 lesson 文件 (按需加载, 详细根因分析)

### 类比 N188/N190/N191/N192/N193 模式

这是第 6 次"AI 反复违反 + 用户反馈 + 沉淀到 L0"的循环:
- N188: conda 环境 → L0
- N190: PowerShell heredoc → L0
- N191: schema 归一化 → L0
- N192: 双调试视角 → L0
- N193: 任务归属 → L0
- **N194: pytest-django 拖慢 → L0**

模式: 每次发现 AI 反复违反的问题, 必须升级到 L0 硬约束, 而不是只写 lesson。

## Related Lessons

- N188: conda gaf 环境规则 — 同样是"AI 反复违反 + 升级到 L0"模式
- N185: 测试覆盖盲点 — AI 思考范围, 但不涉及跑测试慢
- N111: 命令超时 — 长时间命令的背景运行, 但不涉及测试本身慢
