# Spec 34: AuditLog P0 — Wire log_audit to 40+ Sensitive ViewSets (TD-259 #11)

**Status**: ✅ Done (4 Phase all complete)
**Created**: 2026-07-19
**Owner**: AI
**Priority**: P0
**Source**: TD-259 #11 (L3-1 全量扫描 维度④⑤⑥ P0)

## 阶段状态表

| Phase | Status | Completed | Commit | Verification |
|-------|--------|-----------|--------|--------------|
| 1. AuditMixin 基础设施 | ✅ | 2026-07-19 | - | 31/31 tests pass |
| 2. 安全敏感 ViewSet 接入 (accounts + settings + tasks) | ✅ | 2026-07-19 | - | 226/226 tests pass |
| 3. 运营 ViewSet 接入 (agents/pipeline/resources/plugins/scheduler/notifications/monitors/qa/debug/gamestate/executions) | ✅ | 2026-07-19 | - | 1149/1149 tests pass |
| 4. 文档 + i18n + 全量回归 | ✅ | 2026-07-19 | - | 5/5 i18n meta-test pass + TD-259 #11 标 ✅ |

## 背景

TD-259 #11 (P0): AuditLog 模型 + `log_audit()` 助手函数已就位 (accounts/models.py:451-487 + accounts/audit.py:18-30), API 端点 `/api/v2/accounts/audit-logs/` 已存在 (只读 ViewSet), 前端 AuditLogPage.tsx 已实现 (290 行, 表格 + 详情 Drawer + i18n). 但全仓库 **0 个生产调用方** — `log_audit()` 是死代码, AuditLog 表 0 行数据, 所有敏感操作 (用户/账户/任务/设备/配置变更) 都无审计记录.

## 范围

将 `log_audit()` 接入 40+ 敏感 ViewSet + 25+ `@action` 自定义端点, 覆盖:
- **accounts**: UserViewSet / AgentTokenViewSet / APIKeyViewSet / GameAccountViewSet / GameAccountGroupViewSet / GameAccountRotationViewSet / UserSessionViewSet / 2FA 系列 / OAuth / 密码重置
- **settings**: LLMConfigViewSet / FeatureFlagViewSet / AppSettingsViewSet / unattended_strategy_view / cleanup_view / generate_diagnostic
- **tasks**: TaskViewSet / CustomTaskViewSet / ScheduledTaskViewSet / MarketplaceViewSet / TaskFolderViewSet / TaskCloneView / TaskExecuteView / TaskBulkActionView / TaskBindDevicesView / TaskBindAccountsView
- **agents**: AgentViewSet / DeviceViewSet / DeviceGroupViewSet / DeviceRegisterView / EmulatorLifecycleView / DeviceLockView / DeviceUnlockView
- **pipeline**: PipelineViewSet / TaskChainViewSet / RecordingViewSet / TaskChainNodeView
- **resources**: ResourcePackViewSet / TemplateVersionViewSet / TagViewSet / TemplateAnnotationViewSet / template_batch_import_view
- **plugins**: PluginUploadView / PluginInstallView / PluginToggleView / PluginUninstallView / PluginReloadView / PluginSandboxExecView
- **scheduler**: TimeWindowViewSet
- **notifications**: NotificationViewSet / WebhookConfigViewSet / AlertRuleViewSet
- **monitors**: MonitorRuleViewSet
- **protocol**: AgentSessionViewSet
- **qa**: QASessionViewSet / QAMessageViewSet
- **debug**: CrashReportViewSet / DebugLogArchiveViewSet
- **gamestate**: GameProfileViewSet / GameStateRuleViewSet
- **executions**: execution_intervene_view

## 方案选择 (N151 §2.0.4 A/B/C 评估)

| 维度 | A. 手动调用 | B. AuditMixin + @audit_action | C. Middleware 自动 |
|-----|-----------|------------------------|----------------|
| 代码量 | ~120 调用点 × 5 行 = 600 行 | ~40 mixin 继承 + 25 装饰器 = 200 行 | 50 行 middleware |
| 一致性 | 低 (resource_type 字符串散落) | 高 (类属性 + 常量) | 中 (URL 推断不可靠) |
| 自定义 details | 高 (每处显式构造) | 高 (hookable `_build_audit_details`) | 低 (无 serializer 数据) |
| 覆盖 @action 端点 | ✅ 显式调用 | ✅ `@audit_action` 装饰器 | ⚠️ 误判风险 (search/validate 等非写操作) |
| 新 ViewSet 强制性 | ❌ 易忘 | ⚠️ 需 meta-test 强制 | ✅ 自动 |
| 递归风险 (AuditLog 自身) | 无 | 无 | 高 (AuditLog 写入触发再审计) |
| 性能 | 同步 | 同步 | 全请求拦截 |
| **N167 七维度评分** | 12/21 | **20/21** | 11/21 |

**决策**: Approach B (AuditMixin + `@audit_action` 装饰器)
- 拒绝 A: 600 行重复样板, 一致性低
- 拒绝 C: 误判风险 + details 丢失 + 递归风险, N167 维度1/2/4/6 均不达标

## 设计

### 1. AuditMixin (`backend/gaf_core/mixins/audit.py`, 新建)

```python
class AuditMixin:
    """DRF mixin: auto-call log_audit on perform_create/update/destroy.
    
    Subclass must set `audit_resource_type` (or rely on model_name fallback).
    Override `_build_audit_details(action, instance)` for custom details payload.
    """
    audit_resource_type: str | None = None
    audit_resource_id_attr: str = 'pk'
    audit_log_create: bool = True
    audit_log_update: bool = True
    audit_log_destroy: bool = True

    def perform_create(self, serializer):
        super().perform_create(serializer)
        if self.audit_log_create:
            self._log_audit('create', serializer.instance)

    def perform_update(self, serializer):
        old_instance = self.get_object() if self.audit_log_update else None
        super().perform_update(serializer)
        if self.audit_log_update:
            self._log_audit('update', serializer.instance, old_instance=old_instance)

    def perform_destroy(self, instance):
        if self.audit_log_destroy:
            self._log_audit('delete', instance)
        super().perform_destroy(instance)

    def _log_audit(self, action, instance, *, old_instance=None):
        from accounts.audit import log_audit
        log_audit(
            user=self.request.user,
            action=action,
            resource_type=self.audit_resource_type or instance._meta.model_name,
            resource_id=str(getattr(instance, self.audit_resource_id_attr, '')),
            details=self._build_audit_details(action, instance, old_instance=old_instance),
            ip_address=_get_client_ip(self.request),
        )

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Override per ViewSet for custom details. Default: empty dict."""
        return {}

    @staticmethod
    def _get_client_ip(request):
        # Use shared helper in gaf_core
        ...
```

### 2. `@audit_action` 装饰器 (`backend/gaf_core/mixins/audit.py`, 同文件)

```python
def audit_action(action: str, resource_type: str, resource_id_kw: str = 'pk'):
    """Decorator for @action methods: wraps to call log_audit after success.
    
    Usage:
        @action(detail=True, methods=['post'])
        @audit_action('execute', 'task')
        def execute(self, request, pk=None):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            response = func(self, request, *args, **kwargs)
            from accounts.audit import log_audit
            log_audit(
                user=request.user,
                action=action,
                resource_type=resource_type,
                resource_id=str(kwargs.get(resource_id_kw, '')),
                details={'endpoint': request.path, 'method': request.method},
                ip_address=_get_client_ip(request),
            )
            return response
        return wrapper
    return decorator
```

### 3. resource_type 常量 (`backend/gaf_core/audit_constants.py`, 新建)

```python
class AuditResourceType:
    USER = 'user'
    TASK = 'task'
    DEVICE = 'device'
    RESOURCE_PACK = 'resource_pack'
    API_KEY = 'api_key'
    FEATURE_FLAG = 'feature_flag'
    GAME_ACCOUNT = 'game_account'
    GAME_PROFILE = 'game_profile'
    # ... new ones (Phase 1 full list)
    PIPELINE = 'pipeline'
    SCHEDULED_TASK = 'scheduled_task'
    PLUGIN = 'plugin'
    # ... etc
```

对齐前端 `AuditLogPage.tsx` 的 `RESOURCE_TYPE_LABEL_KEYS`.

### 4. IP 提取 helper (`backend/gaf_core/audit_constants.py` 或 `gaf_core/utils.py`)

```python
def _get_client_ip(request):
    """Extract client IP, honoring X-Forwarded-For (first IP) for reverse proxy."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
```

### 5. details JSON shape 约定

- create: `{'created': {'field1': 'value1', ...}}` (filtered, exclude sensitive)
- update: `{'before': {...}, 'after': {...}}` (diff only, exclude sensitive)
- delete: `{'deleted_id': pk, 'deleted_repr': str(instance)}`
- @action: `{'endpoint': request.path, 'method': request.method, 'kwargs': kwargs}`

**敏感字段过滤硬约束**: 密码类字段 (`password`, `password_hash`, `secret`, `token`, `api_key`) 永不入 details. 推荐用 model field `sensitive_fields` 属性或显式 allow-list.

### 6. Meta-test (Phase 4 收尾)

`backend/tests/test_audit_coverage.py` (新建):
- 扫描 `backend/*/views.py` 所有 `ViewSet` 类
- 白名单 (只读 ViewSet 如 AuditLogViewSet / LoginHistoryViewSet 等)
- 断言: 所有非白名单 ViewSet 必须 `inherit AuditMixin` OR 显式调用 `log_audit` OR 标 `audit_exempt = True`
- 失败时打印缺失 ViewSet 列表

## Phase 拆分

### Phase 1: 基础设施 (estimated 200 行)
- [ ] 新建 `backend/gaf_core/mixins/audit.py` (AuditMixin + @audit_action 装饰器)
- [ ] 新建 `backend/gaf_core/audit_constants.py` (AuditResourceType 常量 + _get_client_ip helper)
- [ ] 单元测试 `backend/gaf_core/tests/test_audit_mixin.py` (覆盖 create/update/destroy + @action + sensitive field filter + IP extraction)
- [ ] 更新 `backend/gaf_core/mixins/__init__.py` 导出 AuditMixin

### Phase 2: 安全敏感 ViewSet (accounts + settings + tasks, estimated 300 行)
- [ ] accounts app: UserViewSet / AgentTokenViewSet / APIKeyViewSet / GameAccountViewSet / GameAccountGroupViewSet / GameAccountRotationViewSet / UserSessionViewSet / 2FA 系列 / OAuth / 密码重置 (~18 ViewSets/views)
- [ ] settings app: LLMConfigViewSet / FeatureFlagViewSet / AppSettingsViewSet / unattended_strategy_view / cleanup_view / generate_diagnostic (~6 ViewSets/views)
- [ ] tasks app: TaskViewSet + @action (execute/cancel/clone/bulk/bind-devices/bind-accounts/parallel-config) / CustomTaskViewSet / ScheduledTaskViewSet + @action (toggle) / MarketplaceViewSet / TaskFolderViewSet (~10 ViewSets/views)
- [ ] 每 ViewSet 测试增加 audit log 调用断言
- [ ] 阶段验收: 跑 `pytest backend/accounts/ backend/settings/ backend/tasks/` + 手动触发现 AuditLogPage 显示新记录

### Phase 3: 运营 ViewSet (agents/pipeline/resources/plugins/scheduler/notifications/monitors/protocol/qa/debug/gamestate/executions, estimated 400 行)
- [ ] agents app: AgentViewSet / DeviceViewSet / DeviceGroupViewSet / DeviceRegisterView / EmulatorLifecycleView / DeviceLockView / DeviceUnlockView (~7 ViewSets/views)
- [ ] pipeline app: PipelineViewSet / TaskChainViewSet / RecordingViewSet / TaskChainNodeView (~4 ViewSets)
- [ ] resources app: ResourcePackViewSet / TemplateVersionViewSet / TagViewSet / TemplateAnnotationViewSet / template_batch_import_view (~5 ViewSets)
- [ ] plugins app: 6 个 function-based views
- [ ] scheduler / notifications / monitors / protocol / qa / debug / gamestate / executions: ~10 ViewSets/views
- [ ] 每 ViewSet 测试增加 audit log 调用断言
- [ ] 阶段验收: 全量 `pytest backend/`

### Phase 4: 文档 + i18n + 全量回归 (estimated 100 行)
- [ ] `docs/standards/api-contract.md` 新增 §16 "Audit Log" 节: 端点 + resource_type 词表 + details JSON shape 约定 + 敏感字段过滤硬约束
- [ ] `frontend/src/pages/System/AuditLogPage.tsx`: RESOURCE_TYPE_LABEL_KEYS 扩展到 Phase 1-3 全部 resource_type (~25 个)
- [ ] `frontend/src/locales/*/auditLog.json`: 新增 resource_* 翻译 key
- [ ] `backend/tests/test_audit_coverage.py` meta-test (扫描所有 ViewSet, 强制 AuditMixin/log_audit/audit_exempt)
- [ ] 全量回归: `pytest backend/` + `npm run build` + 浏览器手测 AuditLogPage 显示真实数据
- [ ] `docs/general/tech-debt/active.md`: TD-259 #11 标 ✅ FIXED + commit hash + evidence

## 验收标准

### Phase 1 验收
- `AuditMixin` 单元测试通过 (create/update/destroy/@action/sensitive filter/IP)
- `_get_client_ip` 处理 X-Forwarded-For + REMOTE_ADDR
- `AuditResourceType` 常量覆盖前端已有 8 个 resource_type

### Phase 2 验收
- accounts/settings/tasks 三 app 的所有非只读 ViewSet 继承 AuditMixin 或使用 @audit_action
- 跑 `pytest backend/accounts/ backend/settings/ backend/tasks/` 全过
- 手动测试: 登录 admin → 创建 user → 查看 AuditLogPage 显示 "create user" 记录

### Phase 3 验收
- 全部 40+ ViewSet 接入完成
- 跑 `pytest backend/` 全过 (无回归)
- 手动测试: 关键操作 (执行任务 / 安装插件 / 修改 feature flag / 上传 resource pack) 都产生 AuditLog 记录

### Phase 4 验收 (全量回归)
- api-contract.md §16 完成
- 前端 AuditLogPage 全部 25+ resource_type 都有 i18n 标签
- `test_audit_coverage.py` meta-test 通过 (无 ViewSet 漏接)
- TD-259 #11 标 ✅ FIXED

## N167 七维度评分 (Approach B)

| 维度 | 评分 | 说明 |
|-----|-----|------|
| 1. 架构长远性 | 3/3 | AuditMixin 在 gaf_core (跨 app 共享), resource_type 常量统一, 与现有 mixin 模式一致 |
| 2. 全局归一化 | 3/3 | 全部 ViewSet 走同一 mixin, IP/details/resource_type 三处统一 |
| 3. 新旧兼容方案 | 3/3 | 单人自用项目, 一次性切换, 无过渡逻辑 |
| 4. 现有业务完善 | 2/3 | 覆盖全部 40+ ViewSet, 但 @action 自定义端点 details 较简略 (endpoint+method) |
| 5. 性能资源优化 | 2/3 | log_audit 已是非阻塞 try/except, 但同步写 DB; 高频写端点 (如 device screenshot) 不接入 |
| 6. 安全合规加固 | 3/3 | 敏感字段过滤硬约束 + IP 提取 + 2FA 系列全审计 |
| 7. 长期维护成本 | 3/3 | meta-test 强制新 ViewSet 接入, 文档 + i18n + 测试齐全 |
| **总分** | **19/21** | ≥ 19 阈值 → AI 可自决, 但 spec 规模 > 500 行 + 涉及全仓库 ViewSet, 仍走 NotifyUser |

## 风险 + 缓解

| 风险 | 缓解 |
|-----|------|
| `details` 含敏感字段 (password/api_key) | `_build_audit_details` 默认空, 各 ViewSet 显式 allow-list; 单元测试覆盖 |
| `@action` 装饰器顺序冲突 (DRF @action + audit_action) | `@audit_action` 在 `@action` 内层 (装饰器就近原则); 测试覆盖 |
| 循环 import (gaf_core → accounts.audit → accounts.models) | `_log_audit` 内 lazy import `from accounts.audit import log_audit` (已是现有模式) |
| 性能: 同步 DB 写阻塞请求 | log_audit 已 try/except 非阻塞; 高频写端点 (screenshot/click) 不接入; 必要时改 Celery 异步 (Phase 5+ 评估) |
| Meta-test 误报 (只读 ViewSet 漏白名单) | Phase 4 收尾时跑 `test_audit_coverage.py` 调整白名单 |

## 关联

- TD-259 #11 (本 spec 闭环)
- TD-141 (spec-29 agents app 重构, 独立 spec — 不合并, 但 Phase 3 agents app 接入会与 spec-29 Phase 1 重叠)
- 前端 AuditLogPage.tsx (已实现, Phase 4 仅扩展 i18n key)
- `accounts/migrations/0014_auditlog.py` (历史 migration, log_audit 写入端已就位)

## 不可执行项 (本 spec 不做)

- AuditLog 表归档/清理策略 (TD-252 evidence 机制可借鉴, 独立 spec)
- AuditLog 实时 WS 推送到管理员 (独立 feature, 当前 AuditLogPage 轮询足够)
- 已废弃 endpoints (旧 AgentConsumer ACK 系列) 的审计 — 与 TD-141 合并 spec-29 处理
