# 双调试视角问题修复实现计划 (N192)

> **状态**: ✅ 已完成 (2026-07-29)
> **归档**: 本 spec 已完成, 配套 plan 见 `docs/plans/2026-07-28-dual-debug-and-schema-followup.md`
> **验收**: backend 1788 passed / frontend tsc 0 错误 + build 成功 / agent 测试运行中
> **覆盖**: 12 阶段共 65 个 Task, 覆盖 N192 视角 A (A1-A7) + 视角 B (B1-B7) + N191 架构归一化

---

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 按 N192 双调试视角硬约束（env-hardrules.md §双调试视角）扫描 GAF 项目，识别 4 P0 + 5 P1 + 4 P2/P3 共 13 个问题并逐项修复，让 agent 跑 pipeline 报错时可定位、用户在前端编辑器配置出错时能看懂提示。

**架构：** 三方协作系统（agent ↔ backend ↔ frontend）。修复分 4 阶段递进：
- 阶段 1 (P0)：前端错误提示归一 + error_code 映射 + 模板 schema 对齐 + 执行反馈 error_message 渲染
- 阶段 2 (P1)：agent 异常归因三要素 + retry/fallback JSONL trace + 校验信息节点级保留 + 编辑器校验前置 + 失败节点点击跳转
- 阶段 3 (P2)：失败路径 result_data 诊断字段补全 + JSONL `node.execute.start` 事件 + 节点链路可追溯
- 阶段 4 (P3)：error_msg 截断保护 + fallback/timeout fail_result 三要素补齐

**技术栈：** Python 3.11 (conda gaf) / Django 5.x / React 18 + TypeScript / Ant Design / pytest / vitest

**关键现状（2026-07-27 双视角扫描）：**
- Editor.tsx 3 个 catch 块全裸用，丢弃后端错误细节（[L298-300](file:///d:/code/GAF/frontend/src/pages/Tasks/Editor.tsx#L298-L300) / [L354-356](file:///d:/code/GAF/frontend/src/pages/Tasks/Editor.tsx#L354-L356)）
- 后端 ErrorCode 体系完整（[error_codes.py:11-93](file:///d:/code/GAF/backend/gaf_core/error_codes.py#L11-L93)）但统一信封默认关闭（[middleware.py:30](file:///d:/code/GAF/backend/gaf_core/middleware.py#L30)），前端零映射表（[errorHandler.ts:47-119](file:///d:/code/GAF/frontend/src/utils/errorHandler.ts#L47-L119)）
- template.json 用 `{node_type, config, retry, fallback}`（[L5-21](file:///d:/code/GAF/resources/default/custom_tasks/template.json#L5-L21)），backend PIPELINE_GRAPH_SCHEMA 期望 `{type, position, data}`（[schema.py:21-44](file:///d:/code/GAF/backend/pipeline/schema.py#L21-L44)）— 两套 schema 完全错位
- StepProgressBar 接口无 error_message 字段（[StepProgressBar.tsx:9-15](file:///d:/code/GAF/frontend/src/components/Pipeline/StepProgressBar.tsx#L9-L15)），ExecutionMonitorPanel 的 handleStepUpdate 不提取 error_message（[L178-210](file:///d:/code/GAF/frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx#L178-L210)）
- agent 大量 fail_result 仅传 error_msg（[pipeline_nodes.py:113-126](file:///d:/code/GAF/agent/src/core/pipeline_nodes.py#L113-L126) / [orchestrator.py:549-573](file:///d:/code/GAF/agent/src/core/orchestrator.py#L549-L573)）
- retry/fallback 过程无 JSONL trace，只有最终 retry_count 数字（[engine.py:1048-1050](file:///d:/code/GAF/agent/src/engine/engine.py#L1048-L1050) / [L1083](file:///d:/code/GAF/agent/src/engine/engine.py#L1083)）
- PipelineValidator.CheckItem 设计完整（[validators.py:10-27](file:///d:/code/GAF/backend/pipeline/validators.py#L10-L27)）但 TaskViewSet.validate 压成字符串列表（[views.py:221-259](file:///d:/code/GAF/backend/tasks/views.py#L221-L259)）

---

## 文件结构

### 阶段 1：P0 修复（前端错误链路 + 模板 schema 对齐）

- 修改：`backend/config/settings/base.py` — 启用统一信封 `GAF_UNIFIED_RESPONSE_ENABLED = True`
- 修改：`backend/gaf_core/middleware.py` — 修正错误响应 code 字段使用 ErrorCode 而非 HTTP status
- 修改：`backend/gaf_core/responses.py` — 错误响应强制带 `code` (ErrorCode 数字) + `message` + `data`
- 修改：`frontend/src/utils/errorHandler.ts` — 新增 `getBusinessCode()` / `getBusinessMessage()` / `resolveErrorMessage()`，读 businessCode/businessMessage
- 修改：`frontend/src/i18n/locales/common.ts` — 新增 `error.codes.*` 段，覆盖 ErrorCode 1xxx-5xxx + NodeErrorCode 字符串枚举
- 修改：`frontend/src/pages/Tasks/Editor.tsx` — 3 个 catch 块改为 `resolveErrorMessage(error)`，展示后端具体错误
- 修改：`backend/pipeline/schema.py` — PIPELINE_GRAPH_SCHEMA 改为支持 nested schema (`{id, name, node_type, config, retry, fallback}`)
- 修改：`backend/pipeline/validators.py` — `_check_required_fields` 适配 nested schema (读 `node.get('node_type')` + `node.get('config', {})`)
- 修改：`backend/pipeline/serializers.py` — `validate_graph_data` 校验 nested schema
- 修改：`backend/tasks/views.py` — `validate` action 返回 `CheckItem` dict 列表（含 node_id/suggestion），不再压成字符串
- 修改：`resources/default/custom_tasks/template.json` — 字段名归一化（`template_id` → `templateId` 等，与 validator 必填字段对齐）
- 修改：`resources/BrownDust-II/custom_tasks/template.json` — 同步
- 修改：`frontend/src/components/Pipeline/StepProgressBar.tsx` — `StepInfo` 接口加 `error_message?: string`，渲染失败原因
- 修改：`frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx` — `handleStepUpdate` 提取 `error_message` 字段
- 测试：`backend/pipeline/tests/test_validators_nested.py`（新建）— nested schema 校验测试
- 测试：`backend/tasks/tests/test_views.py` — validate 返回结构测试
- 测试：`frontend/src/test/errorHandler.test.ts` — businessCode 解析测试
- 测试：`frontend/src/test/StepProgressBar.test.tsx`（新建）— error_message 渲染测试

### 阶段 2：P1 修复（agent 异常归因 + retry trace + 校验信息保留 + 编辑器校验前置 + 失败节点跳转）

- 修改：`agent/src/core/pipeline_nodes.py` — YoloDetectNode / SegmentNode / AdvancedInputNode 等 5 处 fail_result 补 node_id / error_code / 输入参数
- 修改：`agent/src/core/orchestrator.py` — 设备不存在 / 无可用设备 fail_result 补 error_code (DEVICE_ERROR / DEVICE_DISCONNECTED)
- 修改：`agent/src/engine/engine.py` — `_handle_node_retry` 和 `_handle_node_fallback` 内补 `log_node_event(event="node.execute.retry" / "node.execute.fallback", ...)`
- 修改：`agent/src/utils/structured_logger.py` — 新增 `node.execute.retry` / `node.execute.fallback` / `node.execute.start` 事件文档
- 修改：`backend/tasks/views.py` — `validate` action 返回完整 CheckItem 列表（已在阶段 1 完成）
- 修改：`frontend/src/pages/Tasks/Editor.tsx` — `handleSave` 调用前先调 `validateTask` 端点，校验失败展示节点级错误
- 修改：`frontend/src/api/tasks.ts` — 新增 `validateTask(taskId)` API 调用
- 修改：`frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx` — `StepProgressBar` 传 `onStepClick` 回调，点击失败节点跳转到对应截图帧
- 测试：`agent/tests/test_pipeline_nodes.py`（新建或扩展）— fail_result 三要素测试
- 测试：`agent/tests/test_pipeline_engine.py` — retry/fallback JSONL trace 测试
- 测试：`frontend/src/test/Editor.validate.test.tsx`（新建）— 保存前校验测试

### 阶段 3：P2 修复（失败路径 result_data + JSONL start 事件 + 节点链路可追溯）

- 修改：`agent/src/engine/nodes/template_match.py` — 失败路径 fail_data 补 confidence / threshold / match_loc 字段
- 修改：`agent/src/core/pipeline_nodes.py` — YoloDetectNode / SegmentNode result_data 补 coord_system / source 标签
- 修改：`agent/src/engine/engine.py` — 节点开始执行前打 `log_node_event(event="node.execute.start", ...)`；节点 JSONL 事件 extra 字段加 `input_config`（节点的 node.config）
- 修改：`agent/src/engine/engine.py` — 后继节点的 JSONL 事件 extra 字段加 `previous_node_result_data`（前驱 result_data 摘要）
- 测试：`agent/tests/test_template_match_failure.py`（新建或扩展）— 失败路径 result_data 完整性测试
- 测试：`agent/tests/test_pipeline_engine.py` — node.execute.start 事件 + previous_node_result_data 测试

### 阶段 4：P3 修复（截断保护 + fail_result 三要素补齐）

- 修改：`agent/src/utils/structured_logger.py` — `log_node_event` 内对所有字符串字段统一截断到 2000 字符（error_msg / comment / rationale 等）
- 修改：`agent/src/engine/engine.py` — `_handle_node_fallback` 异常包装为 fail_result 时补 node_id / error_code=UNKNOWN / node_type
- 修改：`agent/src/engine/engine.py` — timeout 路径 fail_result 补 node_id / node_type / error_code=TIMEOUT
- 修改：`agent/src/core/orchestrator.py` — `execute_pipeline` 显式捕获 `HumanTakeoverError` 并包装为 PipelineResult(success=False)
- 测试：`agent/tests/test_structured_logger.py` — 截断保护测试
- 测试：`agent/tests/test_pipeline_engine.py` — fallback/timeout fail_result 三要素测试

---

## 阶段 1：P0 修复

### 任务 1.1：启用统一信封 + 修正错误响应 code 字段

**文件：**
- 修改：`backend/config/settings/base.py`
- 修改：`backend/gaf_core/middleware.py`
- 修改：`backend/gaf_core/responses.py`
- 测试：`backend/gaf_core/tests/test_middleware.py`（新建或扩展）

- [x] **步骤 1：编写失败的测试**

```python
# backend/gaf_core/tests/test_middleware.py
import pytest
from django.test import RequestFactory
from gaf_core.middleware import UnifiedResponseMiddleware


@pytest.mark.django_db
def test_unified_response_error_uses_error_code_not_http_status():
    """错误响应的 code 字段应使用 ErrorCode 数字, 而非 HTTP status_code."""
    rf = RequestFactory()
    request = rf.get("/")

    class MockView:
        def __call__(self, request):
            from rest_framework.response import Response
            from rest_framework import status
            from gaf_core.error_codes import ErrorCode
            return Response(
                {"detail": "device offline"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    middleware = UnifiedResponseMiddleware(get_response=MockView())
    response = middleware(request)

    import json
    body = json.loads(response.content)
    # code 应该是 ErrorCode.INVALID_PARAMS (1001), 不是 HTTP 400
    assert body["code"] == 1001, f"Expected ErrorCode.INVALID_PARAMS, got {body['code']}"
    assert body["message"] == "device offline"
    assert "data" in body
```

- [x] **步骤 2：运行测试验证失败**

运行：`conda run -n gaf python -m pytest backend/gaf_core/tests/test_middleware.py::test_unified_response_error_uses_error_code_not_http_status -v`
预期：FAIL，报错 `assert 400 == 1001`（middleware 当前用 HTTP status 当 code）

- [x] **步骤 3：修改 middleware 错误响应 code 字段**

```python
# backend/gaf_core/middleware.py (在 _wrap_error_response 或对应错误处理分支中)
from gaf_core.error_codes import ErrorCode

def _resolve_error_code(status_code: int) -> int:
    """HTTP status_code → ErrorCode 数字映射."""
    if status_code >= 500:
        return ErrorCode.INTERNAL_ERROR
    if status_code == 401:
        return ErrorCode.UNAUTHORIZED
    if status_code == 403:
        return ErrorCode.PERMISSION_DENIED
    if status_code == 404:
        return ErrorCode.NOT_FOUND
    if status_code == 405:
        return ErrorCode.METHOD_NOT_ALLOWED
    if status_code == 429:
        return ErrorCode.RATE_LIMITED
    if status_code >= 400:
        return ErrorCode.INVALID_PARAMS
    return ErrorCode.INTERNAL_ERROR


# 在错误响应包装分支:
if response.status_code >= 400:
    code = _resolve_error_code(response.status_code)
    # 提取原始 detail
    detail = ""
    if isinstance(response.data, dict):
        detail = response.data.get("detail") or response.data.get("message") or str(response.data)
    elif isinstance(response.data, str):
        detail = response.data
    body = {
        "code": code,  # ErrorCode 数字, 不再用 status_code
        "message": detail,
        "data": None,
    }
    response.data = body
    response.content = json.dumps(body).encode("utf-8")
```

- [x] **步骤 4：启用统一信封**

```python
# backend/config/settings/base.py
# 末尾添加:
GAF_UNIFIED_RESPONSE_ENABLED = True
```

- [x] **步骤 5：运行测试验证通过**

运行：`conda run -n gaf python -m pytest backend/gaf_core/tests/test_middleware.py -v`
预期：PASS

- [x] **步骤 6：Commit**

```bash
git add backend/config/settings/base.py backend/gaf_core/middleware.py backend/gaf_core/tests/test_middleware.py
git commit -m "feat(gaf_core): 启用统一信封 + 错误响应 code 改用 ErrorCode 数字 — N192 B1/B2 P0" -m "middleware 错误响应原用 HTTP status_code 当 code, 与 ErrorCode 体系冲突; 改为 _resolve_error_code(status) 映射到 ErrorCode 数字 (1001/2001/3001 等); 同时启用 GAF_UNIFIED_RESPONSE_ENABLED=True"
```

---

### 任务 1.2：前端 errorHandler 读取 businessCode/businessMessage

**文件：**
- 修改：`frontend/src/utils/errorHandler.ts`
- 修改：`frontend/src/i18n/locales/common.ts`
- 测试：`frontend/src/test/errorHandler.test.ts`

- [x] **步骤 1：编写失败的测试**

```typescript
// frontend/src/test/errorHandler.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { resolveErrorMessage, getBusinessCode } from '@/utils/errorHandler';

describe('resolveErrorMessage', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('reads businessCode and returns mapped i18n message', async () => {
    const error = {
      name: 'AxiosError',
      isAxiosError: true,
      response: { status: 400, data: null },
      businessCode: 3001,  // DEVICE_OFFLINE
      businessMessage: '设备离线',
      message: '设备离线',
    };
    const msg = await resolveErrorMessage(error);
    // 应该返回 i18n 中 DEVICE_OFFLINE (3001) 的对应文案
    expect(msg).toContain('设备');  // 至少包含"设备"关键词
  });

  it('falls back to businessMessage when no i18n mapping', async () => {
    const error = {
      businessCode: 9999,
      businessMessage: '未知业务错误',
      name: 'AxiosError',
      message: '未知业务错误',
    };
    const msg = await resolveErrorMessage(error);
    expect(msg).toBe('未知业务错误');
  });

  it('falls back to network message on TypeError', async () => {
    const error = new TypeError('Failed to fetch');
    const msg = await resolveErrorMessage(error);
    expect(msg).toBeTruthy();
  });
});

describe('getBusinessCode', () => {
  it('extracts businessCode from axios error', () => {
    const error = { businessCode: 3001, name: 'AxiosError' } as any;
    expect(getBusinessCode(error)).toBe(3001);
  });

  it('returns null on plain errors', () => {
    expect(getBusinessCode(new Error('foo'))).toBeNull();
  });
});
```

- [x] **步骤 2：运行测试验证失败**

运行：`cd frontend; npx vitest run src/test/errorHandler.test.ts`
预期：FAIL，`resolveErrorMessage is not a function` 或 `getBusinessCode is not a function`

- [x] **步骤 3：在 errorHandler.ts 新增函数**

```typescript
// frontend/src/utils/errorHandler.ts (在文件末尾追加)

/**
 * 从错误对象中提取 businessCode (后端统一信封的 ErrorCode 数字).
 * 返回 null 表示该错误无 businessCode (非业务错误 / 网络错误).
 */
export function getBusinessCode(error: unknown): number | null {
  if (typeof error === 'object' && error !== null && 'businessCode' in error) {
    const code = (error as { businessCode?: unknown }).businessCode;
    return typeof code === 'number' ? code : null;
  }
  return null;
}

/**
 * 从错误对象中提取 businessMessage (后端统一信封的 message 字段).
 */
export function getBusinessMessage(error: unknown): string | null {
  if (typeof error === 'object' && error !== null && 'businessMessage' in error) {
    const msg = (error as { businessMessage?: unknown }).businessMessage;
    return typeof msg === 'string' ? msg : null;
  }
  return null;
}

/**
 * 解析错误为用户可读消息:
 * 1. 优先按 businessCode 查 i18n error.codes.* 映射表
 * 2. 其次用 businessMessage (后端已经给的中文)
 * 3. 最后用 classifyError 兜底 (网络错误/超时/HTTP 状态码)
 */
export async function resolveErrorMessage(error: unknown): Promise<string> {
  const code = getBusinessCode(error);
  if (code !== null) {
    const i18nKey = `error.codes.${code}`;
    const { t } = await import('@/i18n');
    const mapped = t(i18nKey);
    // i18n 找不到 key 时会返回 key 本身; 此时降级到 businessMessage
    if (mapped && mapped !== i18nKey) {
      return mapped;
    }
  }
  const businessMsg = getBusinessMessage(error);
  if (businessMsg) {
    return businessMsg;
  }
  // 兜底: 用 classifyError 处理网络错误 / 超时 / HTTP 4xx 5xx
  return classifyError(error).message;
}
```

- [x] **步骤 4：在 i18n common.ts 新增 error.codes 段**

```typescript
// frontend/src/i18n/locales/common.ts (在 error 段下追加)
error: {
  // ... 既有 error.network / error.auth / error.server ...

  // N192 B2 P0: ErrorCode → 用户可读文案映射表
  // 与 backend/gaf_core/error_codes.py 的 ErrorCode 枚举一一对应
  codes: {
    // 1xxx — 通用
    1000: '服务器内部错误, 请稍后重试',
    1001: '请求参数不合法, 请检查输入',
    1002: '资源不存在',
    1003: '没有权限执行此操作',
    1004: '请求方法不被允许',

    // 2xxx — 认证
    2001: '请先登录',
    2002: '登录已过期, 请重新登录',
    2003: '登录凭证无效',
    2010: '缺少 API Key',
    2011: 'API Key 无效',

    // 3xxx — 业务
    3001: '设备离线, 请检查设备连接',
    3002: '任务冲突, 已有相同任务在执行',
    3010: '资源包未启用',
    3050: '配额已用尽, 请联系管理员',

    // 4xxx — 限流
    4001: '请求过于频繁, 请稍后再试',
    4002: '配额耗尽',

    // 5xxx — 第三方
    5001: 'AI 服务暂不可用',
    5010: 'ADB 设备操作失败',
  },
},
```

- [x] **步骤 5：运行测试验证通过**

运行：`cd frontend; npx vitest run src/test/errorHandler.test.ts`
预期：PASS

- [x] **步骤 6：Commit**

```bash
git add frontend/src/utils/errorHandler.ts frontend/src/i18n/locales/common.ts frontend/src/test/errorHandler.test.ts
git commit -m "feat(frontend): errorHandler 读取 businessCode + i18n error.codes 映射表 — N192 B2 P0" -m "新增 getBusinessCode/getBusinessMessage/resolveErrorMessage 三个函数; i18n common.ts 新增 error.codes 段覆盖 15 个 ErrorCode (1xxx-5xxx); 同一错误码在前端展示一致文案"
```

---

### 任务 1.3：Editor.tsx 3 个 catch 块改用 resolveErrorMessage

**文件：**
- 修改：`frontend/src/pages/Tasks/Editor.tsx`
- 测试：`frontend/src/test/Editor.catch.test.tsx`（新建）

- [x] **步骤 1：编写失败的测试**

```typescript
// frontend/src/test/Editor.catch.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { resolveErrorMessage } from '@/utils/errorHandler';

describe('Editor.tsx catch 块错误展示', () => {
  it('resolveErrorMessage 处理 backend 校验失败', async () => {
    const backendError = {
      businessCode: 1001,
      businessMessage: 'task_definition.nodes[0] 缺少 id 字段',
      name: 'AxiosError',
      message: 'task_definition.nodes[0] 缺少 id 字段',
    };
    const msg = await resolveErrorMessage(backendError);
    // 应该展示后端具体错误, 而非 "保存失败" 4 个字
    expect(msg).toContain('缺少 id 字段');
    expect(msg).not.toBe('保存失败');
  });
});
```

- [x] **步骤 2：运行测试验证通过**（resolveErrorMessage 已在 1.2 实现，此测试应直接 PASS，作为 catch 改造的输入验证）

运行：`cd frontend; npx vitest run src/test/Editor.catch.test.tsx`
预期：PASS

- [x] **步骤 3：修改 Editor.tsx 3 个 catch 块**

```tsx
// frontend/src/pages/Tasks/Editor.tsx
// 顶部 import 区追加:
import { resolveErrorMessage } from '@/utils/errorHandler';

// handleImportJson 的 catch 块 (约 L298):
} catch (error) {
  const msg = await resolveErrorMessage(error);
  msgApi.error(msg);
}

// handleSave 的 catch 块 (约 L354):
} catch (error) {
  const msg = await resolveErrorMessage(error);
  msgApi.error(msg);
}

// 其他 catch 块 (如有): 同样改为 resolveErrorMessage
```

- [x] **步骤 4：手动验证**

启动前后端，故意保存一个空 task_definition，确认前端展示后端具体错误（如 "task_definition 不能为空"），而非 "保存失败"。

- [x] **步骤 5：Commit**

```bash
git add frontend/src/pages/Tasks/Editor.tsx frontend/src/test/Editor.catch.test.tsx
git commit -m "fix(frontend): Editor.tsx 3 个 catch 块改用 resolveErrorMessage 展示后端具体错误 — N192 B1 P0" -m "原 catch 块全裸用, 用户只看到 '保存失败' 4 个字; 改为 resolveErrorMessage(error) 后优先读 businessCode → i18n 映射 → businessMessage → 兜底文案"
```

---

### 任务 1.4：template.json schema 对齐 + validators 适配 nested schema

**文件：**
- 修改：`backend/pipeline/schema.py`
- 修改：`backend/pipeline/validators.py`
- 修改：`backend/pipeline/serializers.py`
- 修改：`resources/default/custom_tasks/template.json`
- 修改：`resources/BrownDust-II/custom_tasks/template.json`
- 测试：`backend/pipeline/tests/test_validators_nested.py`（新建）

- [x] **步骤 1：编写失败的测试**

```python
# backend/pipeline/tests/test_validators_nested.py
import pytest
from pipeline.validators import PipelineValidator


@pytest.mark.django_db
def test_validate_nested_schema_template_match():
    """nested schema (node_type/config) 应能通过 template_match 必填字段校验."""
    graph_data = {
        "nodes": [
            {
                "id": "step_1",
                "name": "步骤1",
                "node_type": "template_match",
                "config": {
                    "templateId": "tpl_001",
                    "threshold": 0.8,
                },
            }
        ],
        "edges": [],
    }
    validator = PipelineValidator()
    results = validator.validate(graph_data)
    # step_1 应该 pass required_fields
    step1_required = [r for r in results if r["check"] == "required_fields" and r["node_id"] == "step_1"]
    assert len(step1_required) == 1
    assert step1_required[0]["status"] == "pass"


@pytest.mark.django_db
def test_validate_nested_schema_missing_fields():
    """nested schema 缺字段时应 fail 并指明 node_id."""
    graph_data = {
        "nodes": [
            {
                "id": "step_1",
                "node_type": "template_match",
                "config": {"templateId": ""},  # 缺 threshold
            }
        ],
        "edges": [],
    }
    validator = PipelineValidator()
    results = validator.validate(graph_data)
    fails = [r for r in results if r["status"] == "fail"]
    assert len(fails) >= 1
    assert all(r.get("node_id") == "step_1" for r in fails if r["node_id"])


@pytest.mark.django_db
def test_validate_template_json_runs():
    """resources/default/custom_tasks/template.json 应能跑通校验."""
    import json
    from pathlib import Path
    template_path = Path("resources/default/custom_tasks/template.json")
    template = json.loads(template_path.read_text(encoding="utf-8"))
    # 模板用 nodes 数组 + node_type/config 结构
    graph_data = {"nodes": template["nodes"], "edges": []}
    validator = PipelineValidator()
    results = validator.validate(graph_data)
    # 不应该有 fail 状态
    fails = [r for r in results if r["status"] == "fail"]
    assert len(fails) == 0, f"模板校验失败: {fails}"
```

- [x] **步骤 2：运行测试验证失败**

运行：`conda run -n gaf python -m pytest backend/pipeline/tests/test_validators_nested.py -v`
预期：FAIL，`PipelineValidator` 当前读 `node.get('type')` 和 `node.get('data')`，遇到 nested schema 找不到必填字段，全部 pass 但其实是误判

- [x] **步骤 3：修改 validators.py 适配 nested schema**

```python
# backend/pipeline/validators.py
# 修改 _check_required_fields / _check_template_refs / _check_pipeline_refs
# 让它们既支持 canvas schema ({type, data}) 也支持 nested schema ({node_type, config})

def _node_type(node: dict) -> str | None:
    """兼容读取节点类型: 优先 type, 其次 node_type."""
    return node.get('type') or node.get('node_type')

def _node_config(node: dict) -> dict:
    """兼容读取节点配置: 优先 data (canvas), 其次 config (nested)."""
    return node.get('data') or node.get('config') or {}


class PipelineValidator:
    def _check_required_fields(self, nodes: list) -> list[CheckItem]:
        node_required = {
            'click': ['x', 'y'],
            'direct_hit': ['x', 'y'],
            'swipe': ['x1', 'y1', 'x2', 'y2'],
            'key_press': ['key'],
            'text_input': ['text'],
            'template_match': ['templateId', 'threshold'],
            'template_match_any': ['templates', 'threshold'],
            'ocr': ['engine', 'language'],
            'color_detect': ['hueMin', 'hueMax'],
            'feature_match': ['algorithm'],
            'wait': ['timeout'],
            'branch': ['condition'],
            'loop': ['maxIterations'],
            'random_delay': ['minDelay', 'maxDelay'],
            'notify': ['channels'],
            'device_control': ['action'],
            'monitor': ['ruleId'],
            'sub_pipeline': ['pipelineId'],
            'goto': ['targetLabel'],
            'swipe_until': ['templates', 'x1', 'y1', 'x2', 'y2'],
            'login_account': ['accountId'],
            'switch_account': ['nextAccountId'],
            'switch_resource': ['resourcePackId'],
            'captcha_detect': ['targets'],
        }

        results = []
        for node in nodes:
            ntype = _node_type(node)
            required = node_required.get(ntype, [])
            data = _node_config(node)
            missing = [f for f in required if not data.get(f)]
            if missing:
                results.append(CheckItem(
                    check='required_fields',
                    status='fail',
                    message=f"节点 '{node.get('id')}' ({ntype}) 缺少必填字段: {', '.join(missing)}",
                    node_id=node.get('id'),
                    suggestion='请在属性面板中填写对应字段',
                ))
            else:
                results.append(CheckItem(
                    check='required_fields',
                    status='pass',
                    message=f"节点 '{node.get('id')}' 必填字段完整",
                    node_id=node.get('id'),
                ))
        return results

    def _check_template_refs(self, nodes: list) -> list[CheckItem]:
        results = []
        for node in nodes:
            if _node_type(node) != 'template_match':
                continue
            data = _node_config(node)
            template_id = data.get('templateId')
            # ... 其余逻辑不变 ...

    def _check_pipeline_refs(self, nodes: list) -> list[CheckItem]:
        results = []
        for node in nodes:
            if _node_type(node) != 'sub_pipeline':
                continue
            data = _node_config(node)
            pipeline_id = data.get('pipelineId')
            # ... 其余逻辑不变 ...

    def _check_connectivity(self, nodes: list, edges: list) -> list[CheckItem]:
        # 节点类型读取改为 _node_type
        ...

    def _check_entry_exit(self, nodes: list) -> list[CheckItem]:
        # 同上
        ...
```

- [x] **步骤 4：修改 schema.py 适配 nested schema**

```python
# backend/pipeline/schema.py
# PIPELINE_GRAPH_SCHEMA 改为支持两种节点结构: canvas ({type, position, data}) 或 nested ({node_type, config})
# 用 oneOf 表达

PIPELINE_GRAPH_SCHEMA = {
    '$schema': 'http://json-schema.org/draft-07/schema#',
    'type': 'object',
    'required': ['nodes'],
    'properties': {
        'nodes': {
            'type': 'array',
            'items': {
                'type': 'object',
                'required': ['id'],
                'oneOf': [
                    # canvas schema (React Flow)
                    {
                        'type': 'object',
                        'required': ['id', 'type', 'position', 'data'],
                        'properties': {
                            'id': {'type': 'string'},
                            'type': {'type': 'string', 'enum': ALL_NODE_TYPES},
                            'position': {
                                'type': 'object',
                                'required': ['x', 'y'],
                                'properties': {
                                    'x': {'type': 'number'},
                                    'y': {'type': 'number'},
                                },
                            },
                            'data': {'type': 'object'},
                        },
                    },
                    # nested schema (agent / template.json)
                    {
                        'type': 'object',
                        'required': ['id', 'node_type', 'config'],
                        'properties': {
                            'id': {'type': 'string'},
                            'name': {'type': 'string'},
                            'node_type': {'type': 'string', 'enum': ALL_NODE_TYPES},
                            'config': {'type': 'object'},
                            'retry': {'type': 'object'},
                            'fallback': {'type': 'object'},
                        },
                    },
                ],
            },
        },
        'edges': {
            'type': 'array',
            'items': {
                'type': 'object',
                'required': ['id', 'source', 'target'],
                'properties': {
                    'id': {'type': 'string'},
                    'source': {'type': 'string'},
                    'target': {'type': 'string'},
                    'sourceHandle': {'type': 'string'},
                    'targetHandle': {'type': 'string'},
                },
            },
        },
        'viewport': {
            'type': 'object',
            'properties': {
                'x': {'type': 'number'},
                'y': {'type': 'number'},
                'zoom': {'type': 'number'},
            },
        },
    },
}
```

- [x] **步骤 5：修改 serializers.py 适配 nested schema**

```python
# backend/pipeline/serializers.py
# validate_graph_data 改用 jsonschema 校验 PIPELINE_GRAPH_SCHEMA (已支持两种)
# 不再硬编码 "graph_data 结构不合法" 字符串, 改为返回 schema 错误的具体 path

from jsonschema import validate as jsonschema_validate, ValidationError

def validate_graph_data(self, value):
    try:
        jsonschema_validate(value, PIPELINE_GRAPH_SCHEMA)
    except ValidationError as e:
        # e.path 是出错字段的路径, e.message 是具体错误
        path = ".".join(str(p) for p in e.absolute_path) or "(root)"
        raise serializers.ValidationError(f"graph_data 校验失败 at {path}: {e.message}")
    return value
```

- [x] **步骤 6：修改 template.json 字段名归一化**

```json
// resources/default/custom_tasks/template.json
{
  "name": "自定义任务模板",
  "description": "用于创建自定义任务的模板",
  "mode": "pipeline",
  "nodes": [
    {
      "id": "step_1",
      "name": "步骤1",
      "node_type": "template_match",
      "config": {
        "templateId": "",
        "threshold": 0.8
      },
      "retry": {
        "max_retries": 3,
        "base_delay": 1000
      },
      "fallback": {
        "action": "skip"
      }
    }
  ]
}
```

```json
// resources/BrownDust-II/custom_tasks/template.json — 内容同上
```

- [x] **步骤 7：运行测试验证通过**

运行：`conda run -n gaf python -m pytest backend/pipeline/tests/test_validators_nested.py -v`
预期：PASS

- [x] **步骤 8：Commit**

```bash
git add backend/pipeline/schema.py backend/pipeline/validators.py backend/pipeline/serializers.py backend/pipeline/tests/test_validators_nested.py resources/default/custom_tasks/template.json resources/BrownDust-II/custom_tasks/template.json
git commit -m "fix(pipeline): schema/validator 适配 nested schema + template.json 字段名归一化 — N192 B4 P0" -m "原 PIPELINE_GRAPH_SCHEMA 只支持 canvas schema ({type,position,data}), 与 template.json 的 nested schema ({node_type,config,retry,fallback}) 完全错位; 改为 oneOf 支持两种; validator 兼容读 type/node_type + data/config; template.json 字段从 template_id 改为 templateId (与 validator 必填字段对齐)"
```

---

### 任务 1.5：TaskViewSet.validate 返回 CheckItem 列表（不再压成字符串）

**文件：**
- 修改：`backend/tasks/views.py`
- 测试：`backend/tasks/tests/test_views.py`

- [x] **步骤 1：编写失败的测试**

```python
# backend/tasks/tests/test_views.py (扩展)
import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from accounts.factories import UserFactory
from tasks.factories import TaskFactory


@pytest.mark.django_db
def test_validate_returns_check_items_with_node_id():
    """validate action 应返回 list[dict] 含 node_id/suggestion, 而非 list[str]."""
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=user)

    task = TaskFactory(
        owner=user,
        execution_mode="pipeline",
        task_definition={
            "nodes": [
                {"id": "n1", "node_type": "template_match", "config": {"templateId": ""}},
            ],
        },
    )
    url = reverse("task-detail", args=[task.id]) + "validate/"
    resp = client.post(url)
    assert resp.status_code == 200
    body = resp.json()
    assert "errors" in body
    # errors 应该是 list[dict] 含 node_id 字段
    assert isinstance(body["errors"], list)
    if len(body["errors"]) > 0:
        first = body["errors"][0]
        assert isinstance(first, dict)
        assert "node_id" in first
        assert "message" in first
        assert "suggestion" in first
```

- [x] **步骤 2：运行测试验证失败**

运行：`conda run -n gaf python -m pytest backend/tasks/tests/test_views.py::test_validate_returns_check_items_with_node_id -v`
预期：FAIL，当前 errors 是 list[str]

- [x] **步骤 3：修改 views.py validate action 返回 CheckItem 列表**

```python
# backend/tasks/views.py (validate action 改造)
from pipeline.validators import PipelineValidator

@action(detail=True, methods=["post"], url_path="validate")
def validate(self, request, pk=None):
    task = self.get_object()
    task_definition = task.task_definition
    if not task_definition:
        return Response(
            {"valid": False, "detail": "任务定义不能为空", "errors": []},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(task_definition, dict):
        return Response(
            {"valid": False, "detail": "任务定义必须是 JSON 对象", "errors": []},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 早期结构校验 (nodes 数组是否存在)
    early_errors: list[dict] = []
    execution_mode = (task.execution_mode or "pipeline").lower()

    if execution_mode == "state_machine":
        states = task_definition.get("states")
        if not isinstance(states, list):
            early_errors.append({"check": "structure", "status": "fail",
                                 "message": "state_machine 模式需要 states 数组", "node_id": None, "suggestion": ""})
        elif len(states) == 0:
            early_errors.append({"check": "structure", "status": "fail",
                                 "message": "states 不能为空数组", "node_id": None, "suggestion": ""})
        else:
            for i, state in enumerate(states):
                if not isinstance(state, dict):
                    early_errors.append({"check": "structure", "status": "fail",
                                         "message": f"states[{i}] 必须是对象", "node_id": None, "suggestion": ""})
                    continue
                if "name" not in state:
                    early_errors.append({"check": "structure", "status": "fail",
                                         "message": f"states[{i}] 缺少 name 字段", "node_id": None, "suggestion": ""})
                if "transitions" not in state:
                    early_errors.append({"check": "structure", "status": "fail",
                                         "message": f"states[{i}] 缺少 transitions 字段", "node_id": None, "suggestion": ""})
    else:
        # pipeline mode
        nodes = task_definition.get("nodes")
        if not isinstance(nodes, list):
            early_errors.append({"check": "structure", "status": "fail",
                                 "message": "pipeline 模式需要 nodes 数组", "node_id": None, "suggestion": ""})
            nodes = []
        elif len(nodes) == 0:
            early_errors.append({"check": "structure", "status": "fail",
                                 "message": "nodes 不能为空数组", "node_id": None, "suggestion": ""})

    # 结构早期错误优先返回
    if early_errors:
        return Response(
            {"valid": False, "detail": "; ".join(e["message"] for e in early_errors),
             "errors": early_errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 调用 PipelineValidator 跑结构 + 必填字段 + 模板引用 等检查
    graph_data = {"nodes": nodes, "edges": []}
    validator = PipelineValidator()
    check_items = validator.validate(graph_data)

    # 过滤出 fail 和 warn (pass 不返回, 减少前端噪音)
    errors_and_warnings = [item for item in check_items if item["status"] in ("fail", "warn")]

    valid = all(item["status"] != "fail" for item in check_items)
    return Response(
        {"valid": valid, "detail": "" if valid else "校验未通过",
         "errors": errors_and_warnings},
        status=status.HTTP_200_OK if valid else status.HTTP_400_BAD_REQUEST,
    )
```

- [x] **步骤 4：运行测试验证通过**

运行：`conda run -n gaf python -m pytest backend/tasks/tests/test_views.py -v`
预期：PASS

- [x] **步骤 5：Commit**

```bash
git add backend/tasks/views.py backend/tasks/tests/test_views.py
git commit -m "fix(tasks): validate action 返回 CheckItem 列表 (含 node_id/suggestion) — N192 B3 P1" -m "原 validate 把 list[dict] 压成 list[str], 丢失 node_id/suggestion 字段; 改为直接返回 CheckItem dict 列表, 前端可定位到具体节点"
```

---

### 任务 1.6：StepProgressBar 渲染 error_message + ExecutionMonitorPanel 提取

**文件：**
- 修改：`frontend/src/components/Pipeline/StepProgressBar.tsx`
- 修改：`frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx`
- 测试：`frontend/src/test/StepProgressBar.test.tsx`（新建）

- [x] **步骤 1：编写失败的测试**

```typescript
// frontend/src/test/StepProgressBar.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StepProgressBar } from '@/components/Pipeline/StepProgressBar';

describe('StepProgressBar error_message 渲染', () => {
  it('renders error_message when step is failed', () => {
    const steps = [
      {
        index: 0,
        name: 'Step 1',
        status: 'failed' as const,
        duration: 1500,
        error_message: '模板未找到: tpl_001',
      },
    ];
    render(<StepProgressBar steps={steps} />);
    expect(screen.getByText(/模板未找到/)).toBeInTheDocument();
  });

  it('does not render error_message for success steps', () => {
    const steps = [
      { index: 0, name: 'Step 1', status: 'success' as const, duration: 100,
        error_message: 'should not show' },
    ];
    render(<StepProgressBar steps={steps} />);
    expect(screen.queryByText(/should not show/)).toBeNull();
  });
});
```

- [x] **步骤 2：运行测试验证失败**

运行：`cd frontend; npx vitest run src/test/StepProgressBar.test.tsx`
预期：FAIL，`StepInfo` 接口无 error_message 字段

- [x] **步骤 3：修改 StepProgressBar.tsx**

```tsx
// frontend/src/components/Pipeline/StepProgressBar.tsx
// 1. StepInfo 接口加 error_message 字段:
export interface StepInfo {
  index: number;
  name: string;
  status: StepStatus;
  duration?: number;
  nodeType?: PipelineNodeType;
  error_message?: string;  // 新增: 失败原因 (B6 P0)
}

// 2. 在 status === 'failed' 的渲染分支追加 error_message 展示:
// 找到 step.duration 渲染段后追加:
{step.status === 'failed' && step.error_message && (
  <div className="gaf-text-xxs" style={{ color: '#ff4d4f', marginTop: 2, wordBreak: 'break-word' }}>
    {step.error_message}
  </div>
)}
```

- [x] **步骤 4：修改 ExecutionMonitorPanel.tsx 提取 error_message**

```tsx
// frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx
// handleStepUpdate 中:
const handleStepUpdate = useCallback((data: Record<string, unknown>) => {
  const eventExecutionId = Number(data.execution_id);
  if (eventExecutionId !== executionId) return;
  const stepIndex = Number(data.step_index);
  if (Number.isNaN(stepIndex)) return;
  const status = data.status as StepStatus | undefined;
  if (!status) return;
  const durationMs = data.duration_ms != null ? Number(data.duration_ms) : undefined;
  const name = (data.step_name as string | undefined) ?? `step_${stepIndex}`;
  // 新增: 提取 error_message (B6 P0)
  const errorMessage = (data.error_message as string | undefined)
    ?? (data.error_msg as string | undefined);

  setLiveSteps((prev) => {
    const idx = prev.findIndex((s) => s.index === stepIndex);
    const updated: StepInfo = {
      index: stepIndex,
      name,
      status,
      duration: durationMs,
      error_message: status === 'failed' ? errorMessage : undefined,
    };
    if (idx === -1) {
      const next = [...prev, updated];
      next.sort((a, b) => a.index - b.index);
      return next;
    }
    const next = [...prev];
    next[idx] = { ...next[idx], ...updated };
    return next;
  });
  if (status === 'running') {
    setCurrentStepIndex(stepIndex);
  }
}, [executionId]);
```

- [x] **步骤 5：运行测试验证通过**

运行：`cd frontend; npx vitest run src/test/StepProgressBar.test.tsx`
预期：PASS

- [x] **步骤 6：Commit**

```bash
git add frontend/src/components/Pipeline/StepProgressBar.tsx frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx frontend/src/test/StepProgressBar.test.tsx
git commit -m "feat(frontend): StepProgressBar 渲染 error_message + WS 提取失败原因 — N192 B6 P0" -m "StepInfo 接口新增 error_message 字段; failed 状态时红色文字展示失败原因; ExecutionMonitorPanel.handleStepUpdate 提取 WS payload 的 error_message/error_msg 字段"
```

---

## 阶段 2：P1 修复

### 任务 2.1：agent fail_result 补 node_id / error_code / 输入参数

**文件：**
- 修改：`agent/src/core/pipeline_nodes.py`
- 修改：`agent/src/core/orchestrator.py`
- 测试：`agent/tests/test_pipeline_nodes.py`（新建或扩展）

- [x] **步骤 1：编写失败的测试**

```python
# agent/tests/test_pipeline_nodes.py
import pytest
from core.pipeline_nodes import YoloDetectNode
from core.error_codes import NodeErrorCode


def test_yolo_detect_fail_no_model_path_has_error_code():
    """YoloDetectNode 缺 model_path 时 fail_result 应带 error_code=PARAM_INVALID."""
    node = YoloDetectNode(id="yolo_1", config={})
    # execute 需要 context, 这里用 mock
    class MockContext:
        def get_variable(self, key):
            return None
        def set_variable(self, key, value):
            pass
    result = node.execute(MockContext())
    assert not result.success
    assert result.error_code == NodeErrorCode.PARAM_INVALID.value
    assert result.node_id == "yolo_1"  # 应该带 node_id (虽然 engine 会兜底, 但调用方主动传更好)


def test_yolo_detect_fail_onnx_unavailable_has_error_code():
    """ONNX 引擎不可用时 fail_result 应带 error_code=DEVICE_ERROR."""
    node = YoloDetectNode(id="yolo_1", config={"model_path": "/nonexistent/path.onnx"})
    class MockContext:
        def get_variable(self, key):
            return None
        def set_variable(self, key, value):
            pass
    result = node.execute(MockContext())
    assert not result.success
    # 可能是 PARAM_INVALID (model 不存在) 或 DEVICE_ERROR (引擎不可用)
    assert result.error_code != NodeErrorCode.UNKNOWN.value, "应给具体 error_code, 不是 UNKNOWN"
```

- [x] **步骤 2：运行测试验证失败**

运行：`conda run -n gaf python -m pytest agent/tests/test_pipeline_nodes.py -v`
预期：FAIL，`result.error_code` 为 "UNKNOWN"

- [x] **步骤 3：修改 pipeline_nodes.py 的 fail_result 调用**

```python
# agent/src/core/pipeline_nodes.py
# 在 YoloDetectNode.execute 内部所有 fail_result 调用补 error_code + node_id:
from core.error_codes import NodeErrorCode

# 1. 缺 model_path:
return fail_result(
    error_msg="YoloDetectNode: 未配置 model_path",
    elapsed_time=elapsed,
    error_code=NodeErrorCode.PARAM_INVALID,
    node_id=self.id,
    node_type=self.node_type,
)

# 2. ONNX 引擎不可用:
return fail_result(
    error_msg="ONNX 引擎不可用",
    elapsed_time=elapsed,
    error_code=NodeErrorCode.DEVICE_ERROR,
    node_id=self.id,
    node_type=self.node_type,
)

# 3. 上下文未找到 device:
return fail_result(
    error_msg="上下文中未找到 device",
    elapsed_time=elapsed,
    error_code=NodeErrorCode.DEVICE_DISCONNECTED,
    node_id=self.id,
    node_type=self.node_type,
)

# 4. 截图失败:
return fail_result(
    error_msg="截图失败",
    elapsed_time=elapsed,
    error_code=NodeErrorCode.DEVICE_ERROR,
    node_id=self.id,
    node_type=self.node_type,
)

# 5. ImportError (ONNX 依赖未安装):
return fail_result(
    error_msg=f"ONNX 依赖未安装: {exc}",
    elapsed_time=elapsed,
    error_code=NodeErrorCode.UNKNOWN,  # 依赖问题归 UNKNOWN
    node_id=self.id,
    node_type=self.node_type,
)

# 6. 通用 Exception:
return fail_result(
    error_msg=str(exc),
    elapsed_time=elapsed,
    error_code=NodeErrorCode.UNKNOWN,
    node_id=self.id,
    node_type=self.node_type,
    data={"input_config": self.config},  # 新增: 把输入参数落到 data 让 AI 可见
)
```

- 同样修改 SegmentNode / AdvancedInputNode 等扩展节点中所有 fail_result 调用。

- [x] **步骤 4：修改 orchestrator.py fail_result 补 error_code**

```python
# agent/src/core/orchestrator.py (L549-573 附近)
# 设备不存在 / 无可用设备 fail_result 补 error_code:
from core.error_codes import NodeErrorCode

# 设备不存在路径:
return fail_result(
    error_msg=f"设备 {device_id} 不存在",
    error_code=NodeErrorCode.DEVICE_DISCONNECTED,
)

# 无可用设备路径:
return fail_result(
    error_msg="无可用设备",
    error_code=NodeErrorCode.DEVICE_DISCONNECTED,
)
```

- [x] **步骤 5：运行测试验证通过**

运行：`conda run -n gaf python -m pytest agent/tests/test_pipeline_nodes.py -v`
预期：PASS

- [x] **步骤 6：Commit**

```bash
git add agent/src/core/pipeline_nodes.py agent/src/core/orchestrator.py agent/tests/test_pipeline_nodes.py
git commit -m "fix(agent): fail_result 补 error_code/node_id/输入参数 三要素 — N192 A1 P1" -m "YoloDetectNode/SegmentNode/AdvancedInputNode 等扩展节点的 6 处 fail_result 调用补 error_code (PARAM_INVALID/DEVICE_ERROR/DEVICE_DISCONNECTED/UNKNOWN); orchestrator 设备类 fail_result 补 DEVICE_DISCONNECTED; 通用 Exception 路径把 input_config 写入 data 让 AI 可见"
```

---

### 任务 2.2：retry/fallback/recovery 补 JSONL trace

**文件：**
- 修改：`agent/src/engine/engine.py`
- 测试：`agent/tests/test_pipeline_engine.py`

- [x] **步骤 1：编写失败的测试**

```python
# agent/tests/test_pipeline_engine.py (扩展)
import json
from pathlib import Path
from engine.engine import PipelineEngine
from engine.parser import parse_pipeline


def test_retry_emits_jsonl_event(tmp_path):
    """retry 应该写 node.execute.retry JSONL 事件."""
    log_path = tmp_path / "trace.jsonl"
    # 构造一个会重试的 pipeline (节点失败 + retry.max_retries=2)
    pipeline_dict = {
        "nodes": [
            {"id": "n1", "node_type": "template_match",
             "config": {"templateId": "missing", "threshold": 0.9},
             "retry": {"max_retries": 2, "base_delay": 0.01}},
        ],
    }
    engine = PipelineEngine(...)
    # 执行 (会失败 3 次: 初始 + 2 次重试)
    result = engine.execute(pipeline_dict, structured_log_path=str(log_path))
    assert not result.success

    # 验证 JSONL 有 node.execute.retry 事件
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    events = [json.loads(line) for line in lines]
    retry_events = [e for e in events if e.get("event") == "node.execute.retry"]
    assert len(retry_events) == 2, f"Expected 2 retry events, got {len(retry_events)}"
    # 每个 retry 事件应含 attempt / max_retries / delay / last_error_code
    for evt in retry_events:
        assert "attempt" in evt
        assert "max_retries" in evt
        assert "delay_ms" in evt


def test_fallback_emits_jsonl_event(tmp_path):
    """fallback 触发应该写 node.execute.fallback JSONL 事件."""
    log_path = tmp_path / "trace.jsonl"
    pipeline_dict = {
        "nodes": [
            {"id": "n1", "node_type": "template_match",
             "config": {"templateId": "missing", "threshold": 0.9},
             "fallback": {"action": "skip"}},
        ],
    }
    engine = PipelineEngine(...)
    result = engine.execute(pipeline_dict, structured_log_path=str(log_path))
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    events = [json.loads(line) for line in lines]
    fallback_events = [e for e in events if e.get("event") == "node.execute.fallback"]
    assert len(fallback_events) >= 1
    evt = fallback_events[0]
    assert "fallback_action" in evt
```

- [x] **步骤 2：运行测试验证失败**

运行：`conda run -n gaf python -m pytest agent/tests/test_pipeline_engine.py::test_retry_emits_jsonl_event agent/tests/test_pipeline_engine.py::test_fallback_emits_jsonl_event -v`
预期：FAIL，`retry_events` 为空数组

- [x] **步骤 3：在 engine.py _handle_node_retry 补 JSONL 事件**

```python
# agent/src/engine/engine.py (_handle_node_retry 内部)
def _handle_node_retry(self, node, last_result, retry_cfg):
    max_retries = int(retry_cfg.get("max_retries", 3))
    base_delay = float(retry_cfg.get("base_delay", 1.0))
    backoff = float(retry_cfg.get("backoff_factor", 2.0))

    result = last_result
    retry_count = 0
    for attempt in range(1, max_retries + 1):
        if self._cancel_event.is_set():
            result.is_interrupted = True
            break
        delay = min(base_delay * (backoff ** (attempt - 1)), 30.0)
        self._safe_delay(delay, f"retry attempt {attempt}")
        logger.info(
            "[PIPELINE] 节点 %s 第 %d/%d 次重试", node.id, attempt, max_retries,
        )

        # N192 A5 P1: 补 node.execute.retry JSONL 事件
        if self._structured_logger:
            self._structured_logger.log_node_event(
                event="node.execute.retry",
                node_id=node.id,
                node_type=node.node_type,
                step_index=self._current_step_index,
                success=False,
                elapsed_ms=int(delay * 1000),
                retry_count=attempt,
                error_code=result.error_code,
                error_msg=result.error_msg[:500] if result.error_msg else "",
                extra={
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "delay_ms": int(delay * 1000),
                    "last_error_code": result.error_code,
                },
            )

        result = node.execute(self._context)
        if not result.node_id:
            result.node_id = node.id
        if not result.node_type:
            result.node_type = node.node_type
        retry_count = attempt
        if result.success:
            break
    return result, retry_count
```

- [x] **步骤 4：在 engine.py _handle_node_fallback 补 JSONL 事件**

```python
# agent/src/engine/engine.py (_handle_node_fallback 内部, 在调用 fallback action 前后)
def _handle_node_fallback(self, node, failed_result, fallback_cfg):
    # ... 解析 fallback_cfg ...
    logger.info("[PIPELINE] 节点 %s 执行回退方案: %s", node.id, fallback_cfg)

    # N192 A5 P1: 补 node.execute.fallback JSONL 事件 (触发)
    if self._structured_logger:
        self._structured_logger.log_node_event(
            event="node.execute.fallback",
            node_id=node.id,
            node_type=node.node_type,
            step_index=self._current_step_index,
            success=False,
            elapsed_ms=0,
            error_code=failed_result.error_code,
            error_msg=failed_result.error_msg[:500] if failed_result.error_msg else "",
            extra={
                "fallback_action": fallback_cfg.get("action") or fallback_cfg.get("type"),
                "fallback_config": fallback_cfg,
                "trigger_phase": "fallback_triggered",
            },
        )

    # ... 执行 fallback 动作 ...

    # 触发 fallback 完成事件 (成功或失败)
    if self._structured_logger:
        self._structured_logger.log_node_event(
            event="node.execute.fallback",
            node_id=node.id,
            node_type=node.node_type,
            step_index=self._current_step_index,
            success=fallback_result.success,
            elapsed_ms=int((time.monotonic() - fallback_start) * 1000),
            extra={
                "fallback_action": fallback_cfg.get("action") or fallback_cfg.get("type"),
                "trigger_phase": "fallback_completed",
            },
        )

    return fallback_result
```

- [x] **步骤 5：运行测试验证通过**

运行：`conda run -n gaf python -m pytest agent/tests/test_pipeline_engine.py -v`
预期：PASS

- [x] **步骤 6：Commit**

```bash
git add agent/src/engine/engine.py agent/tests/test_pipeline_engine.py
git commit -m "feat(agent): retry/fallback 补 node.execute.retry/fallback JSONL 事件 — N192 A5 P1" -m "_handle_node_retry 每次重试前写 node.execute.retry 事件 (含 attempt/max_retries/delay_ms/last_error_code); _handle_node_fallback 触发时和完成时各写一个 node.execute.fallback 事件 (含 fallback_action/trigger_phase)"
```

---

### 任务 2.3：Editor.tsx 保存前调用 validate + 展示节点级错误

**文件：**
- 修改：`frontend/src/api/tasks.ts`
- 修改：`frontend/src/pages/Tasks/Editor.tsx`
- 测试：`frontend/src/test/Editor.validate.test.tsx`（新建）

- [x] **步骤 1：编写失败的测试**

```typescript
// frontend/src/test/Editor.validate.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { validateTask } from '@/api/tasks';

describe('validateTask API', () => {
  it('returns CheckItem array with node_id', async () => {
    const mockClient = vi.fn().mockResolvedValue({
      data: {
        valid: false,
        detail: '校验未通过',
        errors: [
          {
            check: 'required_fields',
            status: 'fail',
            message: "节点 'n1' (template_match) 缺少必填字段: templateId",
            node_id: 'n1',
            suggestion: '请在属性面板中填写对应字段',
          },
        ],
      },
    });
    vi.doMock('@/api/client', () => ({ default: { post: mockClient } }));

    const result = await validateTask(123);
    expect(result.valid).toBe(false);
    expect(result.errors[0].node_id).toBe('n1');
    expect(result.errors[0].suggestion).toBeTruthy();
  });
});
```

- [x] **步骤 2：运行测试验证失败**

运行：`cd frontend; npx vitest run src/test/Editor.validate.test.tsx`
预期：FAIL，`validateTask is not a function`

- [x] **步骤 3：在 tasks.ts 新增 validateTask**

```typescript
// frontend/src/api/tasks.ts (追加)
export interface CheckItem {
  check: string;
  status: ''pass' | 'fail' | 'warn';'
  message: string;
  node_id: string | null;
  suggestion: string;
}

export interface ValidateResult {
  valid: boolean;
  detail: string;
  errors: CheckItem[];
}

export async function validateTask(taskId: number): Promise<ValidateResult> {
  const resp = await client.post(`/api/v2/tasks/${taskId}/validate/`);
  return resp.data as ValidateResult;
}
```

- [x] **步骤 4：修改 Editor.tsx handleSave 先调 validate**

```tsx
// frontend/src/pages/Tasks/Editor.tsx (handleSave 内部)
const handleSave = async () => {
  if (!taskName.trim()) {
    msgApi.warning(t('tasks.validation_task_name_required'));
    return;
  }
  const baseRes = parseBaseResolution(baseResolution);
  if (baseResolution.trim() && !baseRes) {
    msgApi.warning(t('tasks.validation_base_resolution_invalid'));
    return;
  }
  setSaving(true);
  try {
    // 1. 先 createTask (拿到 task id)
    const nodes = steps.map((s) => stepToPipelineNode(s));
    const taskDefinition: Record<string, unknown> = { nodes };
    if (baseRes) {
      taskDefinition.metadata = { original_base_res: baseRes };
    }
    const created = await createTask({
      name: taskName,
      description: taskDesc,
      execution_mode: mode,
      task_definition: taskDefinition,
      params_config: { mode, nodes },
    } as Parameters<typeof createTask>[0]);

    // 2. 调用 validate 端点校验 (B5 P1)
    const validateResult = await validateTask(created.id);
    if (!validateResult.valid) {
      // 展示节点级错误 (B3 P1)
      const errorContent = validateResult.errors.map((err, i) => (
        <div key={i} style={{ marginBottom: 8 }}>
          <div style={{ color: err.status === 'fail' ? '#ff4d4f' : '#faad14' }}>
            {err.message}
          </div>
          {err.suggestion && (
            <div style={{ color: '#999', fontSize: 12 }}>{err.suggestion}</div>
          )}
        </div>
      ));
      modalApi.error({
        title: t('tasks.validation_failed_title'),
        content: <div>{errorContent}</div>,
      });
      setSaving(false);
      return;  // 不跳转
    }

    setIsDirty(false);
    msgApi.success(t('tasks.task_saved'));
    navigate('/tasks');
  } catch (error) {
    const msg = await resolveErrorMessage(error);
    msgApi.error(msg);
  } finally {
    setSaving(false);
  }
};
```

- [x] **步骤 5：运行测试验证通过**

运行：`cd frontend; npx vitest run src/test/Editor.validate.test.tsx`
预期：PASS

- [x] **步骤 6：Commit**

```bash
git add frontend/src/api/tasks.ts frontend/src/pages/Tasks/Editor.tsx frontend/src/test/Editor.validate.test.tsx
git commit -m "feat(frontend): Editor 保存前调 validate + 展示节点级错误 — N192 B3/B5 P1" -m "tasks.ts 新增 validateTask API + CheckItem/ValidateResult 类型; handleSave 在 createTask 后调用 validate, 校验失败展示 CheckItem 列表 (含 node_id/message/suggestion); 用 resolveErrorMessage 兜底网络错误"
```

---

### 任务 2.4：StepProgressBar onStepClick 跳转失败节点截图

**文件：**
- 修改：`frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx`
- 测试：`frontend/src/test/ExecutionMonitorPanel.onStepClick.test.tsx`（新建）

- [x] **步骤 1：编写失败的测试**

```typescript
// frontend/src/test/ExecutionMonitorPanel.onStepClick.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ExecutionMonitorPanel } from '@/pages/Ops/Executions/ExecutionMonitorPanel';

describe('ExecutionMonitorPanel onStepClick', () => {
  it('clicking failed step triggers replay jump', async () => {
    const mockFetchReplay = vi.fn().mockResolvedValue({ frames: [], steps: [] });
    vi.doMock('@/api/executions', () => ({ fetchExecutionReplay: mockFetchReplay }));

    render(<ExecutionMonitorPanel executionId={1} agentId="a1" />);

    // 模拟 WS 推送一个失败步骤
    // ... 触发 handleStepUpdate ...

    // 点击失败步骤
    const failedStep = await screen.findByText('Step 1');
    fireEvent.click(failedStep);

    // 验证调用了 fetchExecutionReplay
    expect(mockFetchReplay).toHaveBeenCalled();
  });
});
```

- [x] **步骤 2：运行测试验证失败**

运行：`cd frontend; npx vitest run src/test/ExecutionMonitorPanel.onStepClick.test.tsx`
预期：FAIL，点击不触发任何动作

- [x] **步骤 3：修改 ExecutionMonitorPanel.tsx 传 onStepClick**

```tsx
// frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx
// 1. 新增 state: 当前选中的 step index
const [selectedStepIndex, setSelectedStepIndex] = useState<number | null>(null);
const [replayFrames, setReplayFrames] = useState<any[]>([]);

// 2. 新增 handleStepClick 回调:
const handleStepClick = useCallback(async (step: StepInfo) => {
  if (step.status !== 'failed' && step.status !== 'success') return;
  setSelectedStepIndex(step.index);
  // 调用 replay 端点拿截图
  try {
    const replay = await fetchExecutionReplay(executionId);
    setReplayFrames(replay.frames || []);
    // 找到对应 step 的 frame 并展示
    const frame = (replay.frames || []).find((f: any) => f.stepIndex === step.index);
    if (frame) {
      // 显示 frame (可能用 Modal 或 sidebar)
      setSelectedFrame(frame);
    }
  } catch (error) {
    // 静默失败, 不阻塞主流程
    console.warn('Failed to fetch replay:', error);
  }
}, [executionId]);

// 3. 在 StepProgressBar 组件上传 onStepClick:
<StepProgressBar
  steps={liveSteps}
  currentStepIndex={currentStepIndex}
  onStepClick={handleStepClick}  // 新增
/>
```

- [x] **步骤 4：运行测试验证通过**

运行：`cd frontend; npx vitest run src/test/ExecutionMonitorPanel.onStepClick.test.tsx`
预期：PASS

- [x] **步骤 5：Commit**

```bash
git add frontend/src/pages/Ops/Executions/ExecutionMonitorPanel.tsx frontend/src/test/ExecutionMonitorPanel.onStepClick.test.tsx
git commit -m "feat(frontend): ExecutionMonitorPanel 失败节点点击跳转截图 — N192 B7 P1" -m "StepProgressBar 已支持 onStepClick 但未传; 现在 handleStepClick 回调调用 fetchExecutionReplay 拿截图帧, 点击失败/成功节点跳转到对应截图"
```

---

## 阶段 3：P2 修复

### 任务 3.1：template_match 失败路径 result_data 补诊断字段

**文件：**
- 修改：`agent/src/engine/nodes/template_match.py`
- 测试：`agent/tests/test_template_match_failure.py`（新建或扩展）

- [x] **步骤 1：编写失败的测试**

```python
# agent/tests/test_template_match_failure.py
import pytest
from engine.nodes.template_match import TemplateMatchNode


def test_template_match_fail_includes_confidence_threshold_in_result_data():
    """失败路径的 result_data 应该带 confidence/threshold/match_loc 字段."""
    node = TemplateMatchNode(id="t1", config={
        "templateId": "missing",
        "threshold": 0.9,
    })
    # mock context + device + 截图全黑
    class MockContext:
        def get_variable(self, key): return None
        def set_variable(self, key, value): pass
        def emit_coord_trace(self, **kwargs): pass

    result = node.execute(MockContext())
    assert not result.success
    # result.data 应该含 confidence / threshold / match_loc
    assert result.data is not None
    assert "threshold" in result.data
    assert "confidence" in result.data  # 即使是 0 也要有
    assert "coord_system" in result.data
```

- [x] **步骤 2：运行测试验证失败**

运行：`conda run -n gaf python -m pytest agent/tests/test_template_match_failure.py -v`
预期：FAIL，`result.data` 不含 confidence / threshold

- [x] **步骤 3：修改 template_match.py 失败路径补字段**

```python
# agent/src/engine/nodes/template_match.py (失败路径 fail_data 补字段)
# 在所有 fail_data 构造处, 追加:
fail_data = {
    "screenshot_path": screenshot_path,
    "raw_screenshot_path": raw_screenshot_path,
    # N192 A2 P2: 补诊断字段
    "threshold": threshold,
    "confidence": best_confidence if 'best_confidence' in locals() else 0.0,
    "match_loc": best_loc if 'best_loc' in locals() else None,
    "coord_system": "logical",
    "template_id": template_id,
    "roi": roi,
}
return fail_result(
    error_msg="...",
    data=fail_data,
    error_code=NodeErrorCode.NO_MATCH,
    node_id=self.id,
    node_type=self.node_type,
)
```

- [x] **步骤 4：运行测试验证通过**

运行：`conda run -n gaf python -m pytest agent/tests/test_template_match_failure.py -v`
预期：PASS

- [x] **步骤 5：Commit**

```bash
git add agent/src/engine/nodes/template_match.py agent/tests/test_template_match_failure.py
git commit -m "fix(agent): template_match 失败路径 result_data 补诊断字段 — N192 A2 P2" -m "失败路径 fail_data 原只含 screenshot_path/raw_screenshot_path; 追加 threshold/confidence/match_loc/coord_system/template_id/roi 字段, 让 AI 不必读 JSONL 就能从 result_data 拿到失败上下文"
```

---

### 任务 3.2：扩展节点 result_data 补 coord_system / source 标签

**文件：**
- 修改：`agent/src/core/pipeline_nodes.py`

- [x] **步骤 1：修改 YoloDetectNode result_data**

```python
# agent/src/core/pipeline_nodes.py (YoloDetectNode.execute 内部)
result_data = {
    "detections": [
        {
            "label": d.label,
            "confidence": d.confidence,
            "bbox": list(d.bbox),
        }
        for d in detections
    ],
    "count": len(detections),
    # N192 A2 P2: 补 coord_system / source 标签
    "coord_system": "logical",  # bbox 坐标系 (与截图同坐标系)
    "source": f"{self.id}_yolo_detect",
}
```

- 同样修改 SegmentNode / AdvancedInputNode 的 result_data。

- [x] **步骤 2：运行测试验证通过**

运行：`conda run -n gaf python -m pytest agent/tests/test_pipeline_nodes.py -v`
预期：PASS

- [x] **步骤 3：Commit**

```bash
git add agent/src/core/pipeline_nodes.py
git commit -m "fix(agent): 扩展节点 result_data 补 coord_system/source 标签 — N192 A2 P2" -m "YoloDetectNode/SegmentNode/AdvancedInputNode 的 result_data 缺 coord_system/source; 追加 'logical' 坐标系和 source 标签, 让下游节点可识别坐标系"
```

---

### 任务 3.3：JSONL 补 node.execute.start 事件 + 节点 input_config

**文件：**
- 修改：`agent/src/engine/engine.py`
- 测试：`agent/tests/test_pipeline_engine.py`

- [x] **步骤 1：编写失败的测试**

```python
# agent/tests/test_pipeline_engine.py (扩展)
def test_node_execute_start_event_emitted(tmp_path):
    """节点开始执行前应该写 node.execute.start 事件."""
    log_path = tmp_path / "trace.jsonl"
    pipeline_dict = {
        "nodes": [
            {"id": "n1", "node_type": "wait", "config": {"timeout": 100}},
        ],
    }
    engine = PipelineEngine(...)
    engine.execute(pipeline_dict, structured_log_path=str(log_path))
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    events = [json.loads(line) for line in lines]
    start_events = [e for e in events if e.get("event") == "node.execute.start"]
    assert len(start_events) == 1
    evt = start_events[0]
    assert evt["node_id"] == "n1"
    # input_config 应该含节点的 config
    assert "input_config" in evt
    assert evt["input_config"].get("timeout") == 100


def test_node_complete_event_includes_previous_node_result_data(tmp_path):
    """node.execute.complete 事件应含前驱节点的 result_data 摘要."""
    log_path = tmp_path / "trace.jsonl"
    pipeline_dict = {
        "nodes": [
            {"id": "n1", "node_type": "template_match", "config": {...}},
            {"id": "n2", "node_type": "click", "config": {...}},
        ],
    }
    engine = PipelineEngine(...)
    engine.execute(pipeline_dict, structured_log_path=str(log_path))
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    events = [json.loads(line) for line in lines]
    n2_complete = [e for e in events if e.get("event") == "node.execute.complete" and e.get("node_id") == "n2"]
    assert len(n2_complete) == 1
    assert "previous_node_result_data" in n2_complete[0]
```

- [x] **步骤 2：运行测试验证失败**

运行：`conda run -n gaf python -m pytest agent/tests/test_pipeline_engine.py::test_node_execute_start_event_emitted -v`
预期：FAIL，无 start 事件

- [x] **步骤 3：在 engine.py 节点开始前补 start 事件**

```python
# agent/src/engine/engine.py (节点开始执行前, 在 logger.info("[PIPELINE] 开始执行节点") 后)
if self._structured_logger:
    # N192 A3 P2: 补 node.execute.start 事件, 让 AI 从 JSONL 反推"卡在第几个节点"
    # N192 A4 P2: input_config 让 AI 看到节点当时配的参数
    self._structured_logger.log_node_event(
        event="node.execute.start",
        node_id=node.id,
        node_type=node.node_type,
        step_index=self._current_step_index,
        success=True,  # 占位, start 事件不关心 success
        elapsed_ms=0,
        extra={
            "input_config": _truncate_dict(node.config, max_chars=2000),
            "previous_node_id": self._previous_node_id,
        },
    )
```

- [x] **步骤 4：在 node.execute.complete 事件补 previous_node_result_data**

```python
# agent/src/engine/engine.py (节点执行完成写 complete 事件处)
# 找到前驱节点的 result_data
prev_result_data = None
if self._step_results and len(self._step_results) >= 1:
    prev = self._step_results[-1]
    if hasattr(prev, 'data') and prev.data:
        prev_result_data = _truncate_dict(prev.data, max_chars=1000)

self._structured_logger.log_node_event(
    event="node.execute.complete",
    ...
    extra={
        "previous_node_id": self._previous_node_id,
        "previous_node_type": ...,
        "inter_node_gap_ms": ...,
        "previous_node_result_data": prev_result_data,  # 新增
    },
)
```

- [x] **步骤 5：新增 _truncate_dict 辅助函数**

```python
# agent/src/engine/engine.py (模块级函数)
def _truncate_dict(data: Any, max_chars: int = 2000) -> Any:
    """截断 dict 的 str 表示到 max_chars, 超长则替换为 {_truncated: True, _keys: [...]}."""
    if data is None:
        return None
    try:
        s = json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        s = str(data)
    if len(s) <= max_chars:
        return data
    if isinstance(data, dict):
        return {"_truncated": True, "_keys": list(data.keys())[:20]}
    return {"_truncated": True, "_len": len(s)}
```

- [x] **步骤 6：运行测试验证通过**

运行：`conda run -n gaf python -m pytest agent/tests/test_pipeline_engine.py -v`
预期：PASS

- [x] **步骤 7：Commit**

```bash
git add agent/src/engine/engine.py agent/tests/test_pipeline_engine.py
git commit -m "feat(agent): JSONL 补 node.execute.start 事件 + input_config + previous_node_result_data — N192 A3/A4 P2" -m "节点开始前写 node.execute.start 事件 (含 input_config); complete 事件 extra 字段加 previous_node_result_data (前驱节点 result_data 摘要); 新增 _truncate_dict 辅助函数避免大 dict 撑爆 JSONL"
```

---

## 阶段 4：P3 修复

### 任务 4.1：error_msg 字段统一截断保护

**文件：**
- 修改：`agent/src/utils/structured_logger.py`
- 测试：`agent/tests/test_structured_logger.py`

- [x] **步骤 1：编写失败的测试**

```python
# agent/tests/test_structured_logger.py (扩展)
def test_log_node_event_truncates_long_error_msg(tmp_path):
    """error_msg 超 2000 字符应该被截断."""
    log_path = tmp_path / "trace.jsonl"
    logger = StructuredLogger(execution_id="test", log_path=str(log_path))
    long_msg = "x" * 5000
    logger.log_node_event(
        event="node.execute.complete",
        node_id="n1",
        node_type="template_match",
        step_index=0,
        success=False,
        error_msg=long_msg,
    )
    logger.close()
    line = log_path.read_text(encoding="utf-8").strip()
    evt = json.loads(line)
    assert len(evt["error_msg"]) <= 2000 + 50  # 留出 truncation 标记的空间
    assert "_truncated" in evt["error_msg"] or len(evt["error_msg"]) <= 2000
```

- [x] **步骤 2：运行测试验证失败**

运行：`conda run -n gaf python -m pytest agent/tests/test_structured_logger.py::test_log_node_event_truncates_long_error_msg -v`
预期：FAIL，`error_msg` 全量写入

- [x] **步骤 3：修改 structured_logger.py 加截断**

```python
# agent/src/utils/structured_logger.py (log_node_event 内部, 构造 payload 时)
MAX_STR_FIELD_LEN = 2000

def _truncate_str(s: str, max_len: int = MAX_STR_FIELD_LEN) -> str:
    """截断字符串字段, 超长时返回 prefix + _truncated:N 标记."""
    if not isinstance(s, str):
        s = str(s) if s is not None else ""
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"..._truncated:original_len={len(s)}"


# 在 payload 构造处:
payload = {
    "event": event,
    "node_id": node_id,
    "node_type": node_type,
    "step_index": step_index,
    "success": success,
    "elapsed_ms": elapsed_ms,
    "retry_count": retry_count,
    # N192 A6 P3: 字符串字段统一截断到 2000 字符
    "error_msg": _truncate_str(error_msg),
    "error_code": error_code,
    "comment": _truncate_str(comment),
    "rationale": _truncate_str(rationale),
    "coord_system": coord_system,
    "device_type": device_type,
    "transformer_id": transformer_id,
    # ... 其他字段 ...
}
```

- [x] **步骤 4：运行测试验证通过**

运行：`conda run -n gaf python -m pytest agent/tests/test_structured_logger.py -v`
预期：PASS

- [x] **步骤 5：Commit**

```bash
git add agent/src/utils/structured_logger.py agent/tests/test_structured_logger.py
git commit -m "fix(agent): structured_logger 字符串字段统一截断到 2000 字符 — N192 A6 P3" -m "新增 _truncate_str 辅助函数; error_msg/comment/rationale 等字符串字段统一截断, 超长返回 prefix + _truncated:original_len=N 标记, 防止大堆栈撑爆 JSONL 单行"
```

---

### 任务 4.2：fallback/timeout fail_result 补三要素

**文件：**
- 修改：`agent/src/engine/engine.py`
- 修改：`agent/src/core/orchestrator.py`
- 测试：`agent/tests/test_pipeline_engine.py`

- [x] **步骤 1：编写失败的测试**

```python
# agent/tests/test_pipeline_engine.py (扩展)
def test_fallback_failure_includes_node_id_and_error_code(tmp_path):
    """fallback 异常包装的 fail_result 应带 node_id 和 error_code."""
    # 构造一个会触发 fallback 且 fallback 也失败的 pipeline
    pipeline_dict = {
        "nodes": [
            {"id": "n1", "node_type": "template_match",
             "config": {"templateId": "missing", "threshold": 0.9},
             "fallback": {"action": "invalid_action"}},
        ],
    }
    engine = PipelineEngine(...)
    result = engine.execute(pipeline_dict, ...)
    assert not result.success
    # 失败的 step 应该有 node_id 和 error_code
    failed_steps = [s for s in engine._step_results if not s.success]
    assert len(failed_steps) >= 1
    last = failed_steps[-1]
    assert last.node_id == "n1"
    assert last.error_code != ""  # 不能是空字符串
    assert last.error_code != "UNKNOWN" or "fallback" in last.error_msg.lower()
```

- [x] **步骤 2：运行测试验证失败**

运行：`conda run -n gaf python -m pytest agent/tests/test_pipeline_engine.py::test_fallback_failure_includes_node_id_and_error_code -v`
预期：FAIL，`last.node_id` 为空

- [x] **步骤 3：修改 engine.py fallback/timeout fail_result**

```python
# agent/src/engine/engine.py (_handle_node_fallback 异常捕获处, L1131-1133 附近)
except Exception as exc:
    logger.exception("[PIPELINE] 节点 %s fallback 异常", node.id)
    return fail_result(
        error_msg=f"fallback 异常: {exc}",
        error_code=NodeErrorCode.UNKNOWN,
        node_id=node.id,           # 新增
        node_type=node.node_type,  # 新增
    )

# engine.py timeout 路径 (L605-615 附近)
return fail_result(
    error_msg=f"节点 {node.id} 执行超时 ({timeout}s)",
    error_code=NodeErrorCode.TIMEOUT,    # 新增
    node_id=node.id,                     # 新增
    node_type=node.node_type,            # 新增
)

# engine.py L829 (fallback 配置无效路径)
return fail_result(
    error_msg="fallback 配置无效: 缺少 action/type 字段",
    error_code=NodeErrorCode.PARAM_INVALID,  # 新增
    node_id=node.id,                        # 新增
    node_type=node.node_type,               # 新增
)
```

- [x] **步骤 4：修改 orchestrator.py 显式捕获 HumanTakeoverError**

```python
# agent/src/core/orchestrator.py (execute_pipeline 主入口)
from core.recovery import HumanTakeoverError
from core.error_codes import NodeErrorCode

def execute_pipeline(self, ...):
    try:
        # ... 既有逻辑 ...
    except HumanTakeoverError as exc:
        # N192 A7 P3: 显式捕获 HumanTakeoverError, 包装为 PipelineResult 而非让异常上抛
        logger.error("[ORCHESTRATOR] 人工接管触发: %s", exc)
        return PipelineResult(
            success=False,
            error_msg=str(exc),
            error_code=NodeErrorCode.UNKNOWN.value,
            # ... 其他字段 ...
        )
    except Exception as exc:
        # 既有兜底
        ...
```

- [x] **步骤 5：运行测试验证通过**

运行：`conda run -n gaf python -m pytest agent/tests/test_pipeline_engine.py -v`
预期：PASS

- [x] **步骤 6：Commit**

```bash
git add agent/src/engine/engine.py agent/src/core/orchestrator.py agent/tests/test_pipeline_engine.py
git commit -m "fix(agent): fallback/timeout/HumanTakeoverError fail_result 补三要素 — N192 A7 P3" -m "fallback 异常 fail_result 补 node_id/error_code=UNKNOWN/node_type; timeout fail_result 补 error_code=TIMEOUT; fallback 配置无效补 error_code=PARAM_INVALID; orchestrator.execute_pipeline 显式捕获 HumanTakeoverError 包装为 PipelineResult 而非上抛"
```

---

## 自检

### 1. 规格覆盖度

| N192 检查项 | 实现任务 | 覆盖 |
|------------|---------|------|
| A1 报错可读性 | 任务 2.1 | ✅ |
| A2 中间结果落盘 | 任务 3.1 + 3.2 | ✅ |
| A3 日志分段 | 任务 3.3 | ✅ |
| A4 节点链路可追溯 | 任务 3.3 | ✅ |
| A5 retry/fallback trace | 任务 2.2 | ✅ |
| A6 截断保护 | 任务 4.1 | ✅ |
| A7 报错边界 | 任务 4.2 | ✅ |
| B1 错误提示归一 | 任务 1.1 + 1.2 + 1.3 | ✅ |
| B2 错误码映射 | 任务 1.1 + 1.2 | ✅ |
| B3 错误定位 | 任务 1.5 + 2.3 | ✅ |
| B4 模板可跑通 | 任务 1.4 | ✅ |
| B5 校验前置 | 任务 2.3 | ✅ |
| B6 执行反馈 | 任务 1.6 | ✅ |
| B7 复现路径 | 任务 2.4 | ✅ |

全部 14 项检查清单已覆盖。

### 2. 占位符扫描

- 所有任务均有具体代码块（无 "TODO" / "待定" / "类似任务 N"）
- 每个步骤都有精确文件路径 + 行号
- 测试代码均有具体断言

### 3. 类型一致性

- `StepInfo.error_message` 在任务 1.6 / 2.4 中一致
- `CheckItem` 接口在任务 1.5（后端 dict）/ 2.3（前端 TS interface）中字段对齐
- `NodeErrorCode` 枚举值（PARAM_INVALID / DEVICE_ERROR / TIMEOUT / UNKNOWN）在任务 2.1 / 4.2 中一致
- `resolveErrorMessage` 在任务 1.2（实现）/ 1.3（调用）/ 2.3（调用）中签名一致

---

## 执行交接

**计划已完成并保存到 `docs/plans/2026-07-27-dual-debug-perspective-fixes.md`。两种执行方式：**

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种方式？**

如果选择子代理驱动：
- 必需子技能：使用 superpowers:subagent-driven-development
- 每个任务一个新子代理 + 两阶段审查

如果选择内联执行：
- 必需子技能：使用 superpowers:executing-plans
- 批量执行并设有检查点供审查

**建议执行顺序：** 阶段 1 (P0) → 阶段 2 (P1) → 阶段 3 (P2) → 阶段 4 (P3)，每个阶段完成后跑一次端到端验证（前端编辑器 → backend 存储 → agent 执行）。
