---
spec: 2026-08-04-architecture-optimization
title: GAF 架构优化 — Django App 合并 + 架构文档更新
status: completed
created: 2026-08-04
estimated_effort: 4-6 hours
risk: medium
---

# 2026-08-04 架构优化

## 背景

GAF 当前有 **22 个 Django App**，部分 App 职责过瘦（无模型、仅 1 个视图）、部分 App 同属一个业务域但分散管理。经过架构复杂度评估，发现以下问题：

1. **App 粒度过细**: 22 个 App 中，6 个 App 无模型或仅 1 个模型，维护成本高
2. **文档过时**: `overview.md` 仍引用已不存在的 `docs` app
3. **测试文件碎片化**: 部分 App 的测试文件仍偏多，可进一步合并
4. **import 路径分散**: 同业务域的代码分散在不同 App 中，增加认知负担

本次 spec 聚焦 **App 合并 + 测试文件优化 + 架构文档更新**，不涉及架构层面的破坏性改动（如统一 WebSocket）。

## 目标

1. 将 22 个 Django App 合并为 **15 个**（减少 32%）
2. 消除无模型的"瘦 App"，减少项目认知负担
3. 更新架构文档 `overview.md` 反映真实 App 结构
4. 进一步合并碎片化的测试文件
5. 保持向后兼容（API 路由不变，仅内部 import 路径变化）

## 范围

### In Scope

#### App 合并（6 个合并 → 2 个）

| 当前 App | 合并目标 | 理由 |
|---------|---------|------|
| `tracing` | → `gaf_core` | 无模型，只有 middleware + context，与 gaf_core 的基础设施定位一致 |
| `i18n` | → `gaf_core` | 无模型，只有 2 个视图，翻译 API 属基础设施 |
| `search` | → `gaf_core` | 无模型，只有 1 个聚合搜索视图，属基础设施 |
| `metrics` | → `monitors` | 1 个模型 (SLAMetric)，同为运维监控域 |
| `qa` | → `gaf_ai` | 3 个模型，同为 AI 模块，共享 LLM 依赖 |

**合并后 App 数量**: 22 → **17 个**（减少 5 个，23%）

#### 测试文件合并

- 对 `backend/` 下仍偏碎片的测试文件进行进一步合并评估
- 优先合并 `gaf_ai/tests/`（6 个文件）、`scheduler/tests/`（5 个文件）、`protocol/tests/`（8 个文件）

#### 架构文档更新

- `docs/architecture/overview.md`: 更新 App 列表、数量、分组
- `docs/architecture/overview.md` §9: 更新 Backend App 架构章节

### Out of Scope

- 不改 API 路由（`/api/v2/qa/` → `/api/v2/ai/qa/` 等重定向后续考虑）
- 不改前端 API 调用路径
- 不统一 WebSocket 系统（agents + protocol 两套 — 职责分离，非冗余）
- 不合并 StateMachine / ChainManager / Pipeline 三段引擎（StateMachine 是 agent 内部状态机，不暴露到 API）
- 不合并 `device_bridge`（backend 独立使用，非两端重复，agent 端不引用）

## 实施步骤

### Phase 1: tracing → gaf_core（无模型，低风险，~30min）

**为什么 tracing 可以合并**: tracing App 已无模型（TraceSpan 表已删除 F13），仅剩：
- `tracing/middleware.py` — TracingMiddleware（已在 MIDDLEWARE 中引用）
- `tracing/context.py` — trace_id contextvar
- `tracing/tests/` — 测试文件

**步骤**:

1. 创建 `gaf_core/tracing/` 目录，把以下文件移入：
   - `tracing/middleware.py` → `gaf_core/tracing/middleware.py`
   - `tracing/context.py` → `gaf_core/tracing/context.py`
   - 保留 `from tracing.context import current_trace_id` 兼容导入（通过 `gaf_core/tracing/__init__.py` re-export）

2. 更新 `MIDDLEWARE` 配置（`base.py`）:
   ```python
   # 旧: "tracing.middleware.TracingMiddleware"
   # 新: "gaf_core.tracing.middleware.TracingMiddleware"
   ```

3. 全局替换 import 路径:
   - `from tracing.context import ...` → `from gaf_core.tracing.context import ...`
   - `from tracing.middleware import ...` → `from gaf_core.tracing.middleware import ...`

4. 移动测试文件:
   - `tracing/tests/test_tracing.py` → `gaf_core/tests/test_tracing.py`

5. 从 `INSTALLED_APPS` 移除 `"tracing"`

6. 删除 `tracing/` 目录

### Phase 2: i18n → gaf_core（无模型，低风险，~20min）

**步骤**:

1. 创建 `gaf_core/i18n/` 目录，把以下文件移入：
   - `i18n/views.py` → `gaf_core/i18n/views.py`
   - `i18n/urls.py` → `gaf_core/i18n/urls.py`
   - `i18n/serializers.py` → `gaf_core/i18n/serializers.py`（如果有）

2. 更新 `config/urls.py`:
   ```python
   # 旧: path(f"{API_PREFIX}/{_R['i18n']}/", include("i18n.urls"))
   # 新: path(f"{API_PREFIX}/{_R['i18n']}/", include("gaf_core.i18n_urls"))
   ```
   或者直接内联到 `gaf_core/urls.py`。

3. 移动测试文件:
   - `i18n/tests/test_i18n.py` → `gaf_core/tests/test_i18n.py`

4. 从 `INSTALLED_APPS` 移除 `"i18n"`

5. 删除 `i18n/` 目录

### Phase 3: search → gaf_core（无模型，低风险，~20min）

**步骤**:

1. 创建 `gaf_core/search/` 目录，把以下文件移入：
   - `search/views.py` → `gaf_core/search/views.py`
   - `search/urls.py` → `gaf_core/search/urls.py`

2. 更新 `config/urls.py`:
   ```python
   # 旧: path(f"{API_PREFIX}/{_R['search']}/", include("search.urls"))
   # 新: path(f"{API_PREFIX}/{_R['search']}/", include("gaf_core.search_urls"))
   ```

3. 移动测试文件:
   - `search/tests/test_search.py` → `gaf_core/tests/test_search.py`

4. 从 `INSTALLED_APPS` 移除 `"search"`

5. 删除 `search/` 目录

### Phase 4: metrics → monitors（有模型，中风险，~1h）

**metrics 有 1 个模型**: `SLAMetric`，有数据表 `metrics_slametric`，需数据迁移。

**步骤**:

1. 在 `monitors/models.py` 中定义 `SLAMetric` 模型（复制定义，改 `db_table` 为 `monitors_slametric`）

2. 创建数据迁移:
   - 新 migration: 创建 `monitors_slametric` 表
   - 数据迁移: 从 `metrics_slametric` 复制数据到 `monitors_slametric`
   - 后续迁移: 删除 `metrics_slametric` 表

3. 移动文件:
   - `metrics/views.py` → `monitors/views.py`（追加到现有 views）
   - `metrics/serializers.py` → `monitors/serializers.py`
   - `metrics/urls.py` → `monitors/urls.py`（合并到 monitors urls）
   - `metrics/admin.py` → `monitors/admin.py`（合并）

4. 更新 `monitors/urls.py`，添加 SLAMetric 路由:
   ```python
   router.register(r'sla', SLAMetricViewSet)
   ```

5. 更新 `config/urls.py`:
   ```python
   # 旧: path(f"{API_PREFIX}/{_R['metrics']}/", include("metrics.urls"))
   # 新: metrics 路由已合并到 monitors.urls 中
   ```

6. 移动测试文件:
   - `metrics/tests/` → `monitors/tests/`（合并到现有 test_monitors.py）

7. 全局替换 import:
   - `from metrics.models import SLAMetric` → `from monitors.models import SLAMetric`
   - `from metrics.serializers import ...` → `from monitors.serializers import ...`

8. 从 `INSTALLED_APPS` 移除 `"metrics"`

9. 删除 `metrics/` 目录

### Phase 5: qa → gaf_ai（有模型，中高风险，~1.5h）

**qa 有 3 个模型**: QASession, QAMessage, LLMUsageLog，有数据表，需数据迁移。

**步骤**:

1. 在 `gaf_ai/models.py` 中定义 QASession / QAMessage / LLMUsageLog 模型（复制定义，改 `db_table` 前缀为 `gaf_ai_`）

2. 创建数据迁移:
   - 创建 `gaf_ai_qa_session` / `gaf_ai_qa_message` / `gaf_ai_qa_usagelog` 表
   - 从 `qa_qa_session` / `qa_qa_message` / `qa_llmusagelog` 复制数据
   - 删除旧表

3. 移动文件:
   - `qa/views.py` → `gaf_ai/qa_views.py`（或合并到 gaf_ai/views.py）
   - `qa/serializers.py` → `gaf_ai/qa_serializers.py`
   - `qa/urls.py` → `gaf_ai/qa_urls.py`
   - `qa/admin.py` → `gaf_ai/admin.py`（合并）

4. 更新 `gaf_ai/urls.py`，添加 QA 路由:
   ```python
   path("qa/", include("gaf_ai.qa_urls"))
   ```

5. 更新 `config/urls.py`:
   ```python
   # 旧: path(f"{API_PREFIX}/{_R['qa']}/", include("qa.urls"))
   # 新: path(f"{API_PREFIX}/{_R['qa']}/", include("gaf_ai.qa_urls"))
   ```

6. 移动测试文件:
   - `qa/tests/` → `gaf_ai/tests/`（合并到现有测试文件）

7. 全局替换 import:
   - `from qa.models import ...` → `from gaf_ai.models import ...`
   - `from qa.serializers import ...` → `from gaf_ai.qa_serializers import ...`
   - `from qa.views import ...` → `from gaf_ai.qa_views import ...`

8. 从 `INSTALLED_APPS` 移除 `"qa"`

9. 删除 `qa/` 目录

### Phase 6: 测试文件进一步合并（~1h）

**目标**: 减少碎片化测试文件，按逻辑分组合并。

**后端合并方案**:

| App | 当前文件数 | 合并方案 | 合并后 |
|-----|-----------|---------|-------|
| `gaf_ai/tests/` | 6 个 | test_rag + test_llm_router → test_llm.py; test_agent_async + test_agent_tools + test_agent_reasoning → test_agent.py | 4 个 |
| `scheduler/tests/` | 5 个 | test_scheduler + test_unattended + test_recovery → test_scheduler.py; test_chain_completion_hook + test_action_chain 保持独立 | 4 个 |
| `protocol/tests/` | 8 个 | test_message_frame + test_compression → test_protocol.py; 其他保持 | 6 个 |
| `pipeline/tests/` | 8 个 | test_validators + test_validators_nested → test_validators.py; test_recording_converter + test_routine_converter → test_converter.py | 6 个 |

### Phase 7: 架构文档更新（~30min）

**更新文件**:

1. `docs/architecture/overview.md`:
   - §1 项目目录结构: 移除 `docs/` Django app 引用
   - §9 Backend App 架构: 更新为 17 个 App 的新分组
   - 移除 `docs` app 引用（已不存在）
   - 更新 App 数量（22 → 17）

2. `docs/reference/tech-stack.md`:
   - 检查是否有需要更新的 App 列表

## 合并后 App 结构

### 合并后 INSTALLED_APPS（17 个自研 App）

```
accounts       # 用户/游戏账户/2FA/OAuth/API Key
agents         # Agent/Device/DeviceGroup
tasks          # 任务/执行/调度/标签/文件夹
resources      # 资源包/模板/标注
pipeline       # Pipeline JSON + 录制 + TaskChain
scheduler      # 无人值守/恢复引擎/时间窗口/轮换
executions     # 执行记录/步骤/干预
monitors       # 监控规则/事件/告警升级 + SLA 指标 (metrics 合并)
gaf_ai         # LLM Router + RAG + Agent + QA (qa 合并)
skills         # Skill YAML 引擎 + 市场
protocol       # WebSocket 消息帧协议/心跳/配额
debug          # 崩溃报告/日志归档/LLM 分析
gamestate      # OCR 区域识别/阈值触发/GameProfile
settings       # LLMConfig/FeatureFlag/AppSettings
notifications  # 7 渠道通知
plugins        # 插件系统/沙箱
gaf_core       # 全局 middleware/exception/LogEntry + tracing + i18n + search
```

### 合并后 URL 路由（不变）

- API 路由 **不变**，前端不需要改任何代码
- `APP_ROUTES` 映射保持一致
- 仅内部 import 路径变化

## 已知限制（已解决）

1. **API 路由归一化** ✅: `qa` 合并到 `gaf_ai` 后，`/api/v2/qa/` 和 `/api/v2/ai/qa/` 两条路径均可用（`config/urls.py` 直连 + `gaf_ai/urls.py` 嵌套路由）。
2. **数据迁移风险** ✅: metrics 和 qa 的数据迁移已执行成功，验证通过。
3. **import 路径兼容** ✅: 所有旧 import 路径已全局替换，`python manage.py check` 通过。
4. **不涉及架构层合并**: 两套 WebSocket、三段执行引擎等架构问题本次不处理。

## 验证

### Phase 1-3（无模型合并）验证
- `python manage.py check` 通过
- 旧 import 路径全部替换，无 `ModuleNotFoundError`
- 对应的 API endpoint 返回正常（`GET /api/v2/i18n/languages/`、`GET /api/v2/search/` 等）
- 对应测试通过

### Phase 4-5（有模型合并）验证
- `python manage.py makemigrations` 生成正确的迁移
- `python manage.py migrate` 成功
- 数据迁移验证: 旧表数据完整复制到新表
- 旧表删除后，`python manage.py migrate --fake` 完成
- `GET /api/v2/metrics/sla/` 返回正常（通过 monitors 路由）
- `GET /api/v2/qa/` 返回正常（通过 gaf_ai 路由）

### 全量验证
- `python -m pytest backend/ -p no:django` 通过（无模型合并）
- `python -m pytest backend/monitors/tests/` 通过
- `python -m pytest backend/gaf_ai/tests/` 通过
- `python -m pytest backend/gaf_core/tests/` 通过

### 架构文档验证
- `overview.md` §9 的 App 数量 22 → 17
- `overview.md` 项目目录结构移除 `docs/` 引用
- 无过时 App 引用

## 检查清单

### 实施前
- [ ] 确认数据库已备份（metrics / qa 表）
- [ ] 确认 `gaf_init.sh` 通过

### 实施中
- [x] Phase 1: tracing → gaf_core ✅ 2026-08-04
- [x] Phase 2: i18n → gaf_core ✅ 2026-08-04
- [x] Phase 3: search → gaf_core ✅ 2026-08-04
- [x] Phase 4: metrics → monitors ✅ 2026-08-04
- [x] Phase 5: qa → gaf_ai ✅ 2026-08-04（migrate 成功，旧目录已删除）
- [x] Phase 6: 测试文件合并 ✅ 2026-08-04（已在之前会话中合并）
- [x] Phase 7: 架构文档更新 ✅ 2026-08-04

### 实施后
- [x] `python manage.py check` 通过 ✅ 2026-08-04
- [x] `python manage.py migrate` 成功 ✅ 2026-08-04
- [x] backend 测试全部通过 ✅ 2026-08-04（1335 passed）
- [x] 关键 API endpoint 正常返回 ✅ 2026-08-04
- [x] 架构文档更新完成 ✅ 2026-08-04