---
summary: GAF 自定义任务设计
applies_to: ['backend', 'design']
key_decisions:
  - 可视化编辑器设计
  - 推荐使用 Pipeline 路径而非 Task chain
  - Phase 7 实现：state_machine dispatch + Editor 路由暴露 + Task validate 端点
status: deprecated
superseded_by: docs/business/tasks/execution-reality.md
last_updated: 2026-07-27
---

# GAF 自定义任务设计

> **⚠️ DEPRECATED (2026-07-27)**: 本文档基于已废弃的 chain 模式设计。
> spec-2026-07-27-execution-path-unification 完成后，chain 路径整体废弃，
> 所有任务统一走 PipelineEngine。当前任务执行的权威参考请见
> [execution-reality.md](execution-reality.md)。
> 本文档保留作为历史设计参考，不再维护。
>
> 版本：1.2 | 日期：2026-07-05 | 修订：Phase 7 后状态矩阵更新

## 0. 现实状态（2026-07-05 审计，Phase 7 后）

> ✅ **Phase 7 完成**：state_machine 执行模式已接入生产路径，可视化编辑器路由已暴露，Task validate 端点已新增。chain 执行模式的 6 种基础动作限制仍然存在（推荐用 Pipeline 路径）。

| 项 | 文档声称 | 现实代码 | 状态 |
|----|----------|----------|------|
| chain 执行模式 | 支持 find_and_click/template_match/ocr 等 11 种 action | Agent `execute_task` 的 `_run_action` **只支持 6 种基础动作**（click/swipe/key_press/text_input/screenshot/wait） | 🟡 限制（推荐用 Pipeline 路径） |
| state_machine 执行模式 | 完整状态机执行器 | `agent/src/core/orchestrator.py:66-95` `execute_task` 按 `execution_mode` 分发，state_machine 走 `_execute_state_machine()`（Phase 7 commit `-`） | ✅ Phase 7 完成 |
| 可视化编辑器 | TaskEditorPage 完整功能 | `frontend/src/App.tsx:121` 暴露 `/tasks/:taskId/edit` 路由（Phase 7 commit `-`）；`Tasks/Editor.tsx` 完整实现（464 行） | ✅ Phase 7 完成 |
| Task validate 端点 | Task 模型有校验 | `backend/tasks/views.py:184` `TaskViewSet.validate` action（Phase 7 commit `-`） | ✅ Phase 7 完成 |
| 资源包目录结构 | manifest.json + tasks/ + templates/ + config/ + monitors/ | 与代码一致 | ✅ 一致 |

### 0.1 推荐路径

**复杂任务（含模板匹配/OCR/分支/循环）→ 用 Pipeline 路径**，不要用 Task chain。

| 路径 | 模型 | 执行入口 | 支持节点 | 适用场景 |
|------|------|----------|----------|----------|
| **Pipeline**（推荐） | `Pipeline.pipeline_data` (JSON) | `POST /api/v2/pipelines/<pk>/execute/` | 30+ 节点（template_match/ocr/branch/loop/click/swipe/...） | 复杂任务、BD2 迁移 |
| Task chain | `Task.task_definition` (JSON) | `POST /api/v2/tasks/<pk>/execute/` | 6 种基础动作 | 简单脚本（纯点击/滑动/按键） |
| Task state_machine | `Task.task_definition` (JSON) | `POST /api/v2/tasks/<pk>/execute/`（Phase 7 起按 `execution_mode` 分发） | 状态机节点（state/transition） | 状态机任务（Phase 7 起可用） |

详见 [task-execution-reality.md](execution-reality.md)。

---

## 1. 概述

GAF 支持用户通过 JSON 格式定义自定义任务，无需编写 Python 代码。本设计定义 JSON 任务格式、JSON Schema 校验、可视化编辑器设计、参数配置和与原生 Python 任务的统一展示方案。

> ✅ **Phase 7 完成**：state_machine 执行模式已接入，可视化编辑器路由已暴露，Task validate 端点已新增。chain 执行模式仍只支持 6 种基础动作，复杂任务请走 [Pipeline 路径](execution-reality.md)。

---

## 2. JSON 任务定义格式

> **chain schema 已废弃** (spec-2026-07-27-execution-path-unification)。
> 原链式任务 JSON 格式（`execution_mode: "chain"` + `steps: [{action, params, verify, retry, ...}]`）
> 已统一为 pipeline schema（`execution_mode: "pipeline"` + `nodes: [{node_type, config, retry, fallback, post_verify, ...}]`）。
> 旧 chain 字段映射见 `execution-reality.md §1` 表格。下方示例已更新为 pipeline schema。

### 2.1 Pipeline 任务 JSON 格式（线性模式）

```json
{
    "name": "daily_farm",
    "description": "日常刷图任务",
    "execution_mode": "pipeline",
    "params_config": {
        "stage": {
            "type": "string",
            "default": "4-10",
            "label": "关卡",
            "options": ["4-10", "5-5", "6-1"],
            "required": true
        },
        "repeat_count": {
            "type": "integer",
            "default": 3,
            "label": "重复次数",
            "min": 1,
            "max": 99,
            "required": true
        },
        "use_ap_potion": {
            "type": "boolean",
            "default": false,
            "label": "使用体力药水",
            "required": false
        }
    },
    "nodes": [
        {
            "id": "navigate_to_stage",
            "name": "navigate_to_stage",
            "node_type": "template_match",
            "config": {
                "template": "stage_select_button",
                "threshold": 0.85
            },
            "post_verify": {
                "type": "template",
                "target": "stage_list",
                "timeout": 5
            }
        },
        {
            "id": "select_stage",
            "name": "select_stage",
            "node_type": "template_match",
            "config": {
                "template": "stage_{{stage}}",
                "threshold": 0.8
            }
        },
        {
            "id": "start_battle",
            "name": "start_battle",
            "node_type": "template_match",
            "config": {
                "template": "start_battle_button",
                "threshold": 0.9
            },
            "post_verify": {
                "type": "template",
                "target": "battle_start_ui",
                "timeout": 10
            },
            "retry": {
                "max_retries": 3,
                "base_delay": 2000
            }
        },
        {
            "id": "wait_battle_end",
            "name": "wait_battle_end",
            "node_type": "wait",
            "config": {
                "template": "battle_result",
                "timeout": 300
            }
        },
        {
            "id": "claim_reward",
            "name": "claim_reward",
            "node_type": "click",
            "config": {
                "x": 640,
                "y": 600
            },
            "delay_after": 1.5
        }
    ],
    "loop": {
        "count": "{{repeat_count}}",
        "reset_steps": ["navigate_to_stage"]
    }
}
```

### 2.2 状态机任务 JSON 格式

```json
{
    "name": "smart_login",
    "description": "智能登录流程",
    "execution_mode": "state_machine",
    "params_config": {
        "server": {
            "type": "string",
            "default": "CN",
            "label": "服务器",
            "options": ["CN", "JP", "EN"],
            "required": true
        }
    },
    "states": {
        "check_app": {
            "type": "initial",
            "action": "screenshot",
            "description": "检查应用状态"
        },
        "launch_app": {
            "type": "normal",
            "action": "launch_app",
            "action_params": {
                "package": "com.nexon.bluearchive"
            },
            "timeout": 60
        },
        "in_game": {
            "type": "final",
            "description": "成功进入游戏"
        },
        "login_failed": {
            "type": "error",
            "description": "登录失败"
        }
    },
    "transitions": [
        {
            "name": "not_running",
            "from": "check_app",
            "to": "launch_app",
            "trigger": "template",
            "condition": "main_screen",
            "priority": -5
        },
        {
            "name": "already_in_game",
            "from": "check_app",
            "to": "in_game",
            "trigger": "template",
            "condition": "game_main_ui",
            "priority": 40
        },
        {
            "name": "app_launched",
            "from": "launch_app",
            "to": "check_app",
            "trigger": "always"
        }
    ]
}
```

---

## 3. JSON Schema 校验

### 3.1 Pipeline 任务 Schema

```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "GAF Pipeline Task Definition",
    "type": "object",
    "required": ["name", "execution_mode", "nodes"],
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 255,
            "pattern": "^[a-zA-Z0-9_\\u4e00-\\u9fa5]+$"
        },
        "description": {
            "type": "string",
            "maxLength": 2000
        },
        "execution_mode": {
            "type": "string",
            "enum": ["pipeline", "state_machine"]
        },
        "params_config": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["type", "label"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["string", "integer", "float", "boolean", "select"]
                    },
                    "label": {"type": "string"},
                    "default": {},
                    "required": {"type": "boolean"},
                    "min": {"type": "number"},
                    "max": {"type": "number"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                }
            }
        },
        "nodes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "node_type"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "node_type": {
                        "type": "string",
                        "enum": [
                            "screenshot", "click", "template_match",
                            "swipe", "wait", "ocr",
                            "verify", "ocr_check", "start_app",
                            "key_press", "long_press", "text_input",
                            "branch", "loop", "sub_pipeline"
                        ]
                    },
                    "config": {"type": "object"},
                    "pre_verify": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "target": {"type": "string"},
                            "timeout": {"type": "number"}
                        }
                    },
                    "post_verify": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "target": {"type": "string"},
                            "timeout": {"type": "number"}
                        }
                    },
                    "retry": {
                        "type": "object",
                        "properties": {
                            "max_retries": {"type": "integer"},
                            "base_delay": {"type": "number"},
                            "backoff_factor": {"type": "number"}
                        }
                    },
                    "fallback": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "params": {"type": "object"}
                        }
                    },
                    "continue_on_error": {"type": "boolean"},
                    "next_node_id": {"type": "string"}
                }
            }
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from_node": {"type": "string"},
                    "to_node": {"type": "string"}
                }
            }
        }
    }
}
```

### 3.2 校验器实现

```python
import json
from jsonschema import validate, ValidationError
from pathlib import Path

class TaskValidator:
    """任务定义校验器"""

    def __init__(self):
        self._schemas = self._load_schemas()

    def _load_schemas(self) -> dict:
        """加载 JSON Schema"""
        schemas = {}
        schema_dir = Path(__file__).parent / "schemas"
        for schema_file in schema_dir.glob("*.json"):
            with open(schema_file, "r", encoding="utf-8") as f:
                schema = json.load(f)
            schemas[schema_file.stem] = schema
        return schemas

    def validate_pipeline_task(self, task_def: dict) -> list[str]:
        """校验 Pipeline 任务定义，返回错误列表"""
        errors = []
        schema = self._schemas.get("pipeline_task")
        if schema is None:
            return ["Pipeline task schema not found"]

        try:
            validate(instance=task_def, schema=schema)
        except ValidationError as e:
            errors.append(f"Schema validation error: {e.message}")

        errors.extend(self._validate_node_references(task_def))
        errors.extend(self._validate_template_references(task_def))
        errors.extend(self._validate_params_config(task_def))

        return errors

    def validate_state_machine_task(self, task_def: dict) -> list[str]:
        """校验状态机任务定义"""
        errors = []
        schema = self._schemas.get("state_machine_task")
        if schema is None:
            return ["State machine task schema not found"]

        try:
            validate(instance=task_def, schema=schema)
        except ValidationError as e:
            errors.append(f"Schema validation error: {e.message}")

        errors.extend(self._validate_state_references(task_def))
        errors.extend(self._validate_initial_state(task_def))
        errors.extend(self._validate_terminal_states(task_def))

        return errors

    def _validate_node_references(self, task_def: dict) -> list[str]:
        """校验节点引用（next_node_id 必须指向已定义节点）"""
        errors = []
        node_ids = {n.get("id") for n in task_def.get("nodes", [])}
        for node in task_def.get("nodes", []):
            next_id = node.get("next_node_id")
            if next_id and next_id not in node_ids:
                errors.append(f"Node '{node['id']}' references undefined node '{next_id}'")
        return errors

    def _validate_template_references(self, task_def: dict) -> list[str]:
        """校验模板引用"""
        errors = []
        for node in task_def.get("nodes", []):
            config = node.get("config", {})
            # Task 4.43 (P1-26, 2026-07-28): 字段优先级与代码对齐
            # (agent/src/engine/nodes/template_match.py:57 优先 template_id)
            template = config.get("template_id") or config.get("template") or config.get("templateId")
            if template and not self._template_exists(template):
                errors.append(f"Node '{node['id']}' references missing template '{template}'")
        return errors

    def _validate_params_config(self, task_def: dict) -> list[str]:
        """校验参数配置"""
        errors = []
        params_config = task_def.get("params_config", {})
        for key, config in params_config.items():
            if config.get("type") == "integer":
                if "min" in config and "max" in config and config["min"] > config["max"]:
                    errors.append(f"Param '{key}': min > max")
        return errors

    def _validate_state_references(self, task_def: dict) -> list[str]:
        """校验状态引用"""
        errors = []
        state_names = set(task_def.get("states", {}).keys())
        for transition in task_def.get("transitions", []):
            if transition.get("from") not in state_names:
                errors.append(f"Transition '{transition['name']}' references undefined state '{transition['from']}'")
            if transition.get("to") not in state_names:
                errors.append(f"Transition '{transition['name']}' references undefined state '{transition['to']}'")
        return errors

    def _validate_initial_state(self, task_def: dict) -> list[str]:
        """校验初始状态"""
        errors = []
        states = task_def.get("states", {})
        initial_states = [n for n, s in states.items() if s.get("type") == "initial"]
        if len(initial_states) == 0:
            errors.append("No initial state defined")
        elif len(initial_states) > 1:
            errors.append(f"Multiple initial states: {initial_states}")
        return errors

    def _validate_terminal_states(self, task_def: dict) -> list[str]:
        """校验终态可达性"""
        errors = []
        states = task_def.get("states", {})
        terminal_states = {n for n, s in states.items() if s.get("type") in ("final", "error")}
        if not terminal_states:
            errors.append("No terminal state defined")
        return errors

    def _template_exists(self, template: str) -> bool:
        """检查模板是否存在"""
        return True
```

---

## 4. 可视化编辑器设计

### 4.1 编辑器架构

```
┌──────────────────────────────────────────────────────────┐
│  Task Editor                                             │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  工具栏                                               ││
│  │  [添加步骤] [删除] [上移] [下移] [复制] [粘贴]        ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  ┌──────────────────┐  ┌──────────────────────────────┐ │
│  │  步骤列表         │  │  步骤编辑面板                 │ │
│  │                  │  │                              │ │
│  │  1. screenshot   │  │  名称: [screenshot_main]     │ │
│  │  2. find_click   │  │  动作: [find_and_click ▼]   │ │
│  │  3. wait         │  │  模板: [start_button] [浏览] │ │
│  │  4. verify       │  │  阈值: [0.85] ━━━━━━━━━     │ │
│  │  5. click        │  │  验证: [✓] 模板匹配          │ │
│  │                  │  │  超时: [10] 秒               │ │
│  │                  │  │  重试: [3] 次                │ │
│  │                  │  │  延迟: [1.0] 秒              │ │
│  └──────────────────┘  └──────────────────────────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │  预览面板 (JSON / YAML / 流程图)                      ││
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

### 4.2 编辑器功能

| 功能 | 说明 |
|------|------|
| 拖拽排序 | 步骤可通过拖拽调整顺序 |
| 实时预览 | 编辑时实时显示 JSON/YAML 预览 |
| 模板浏览 | 从资源包中选择模板图片 |
| 参数配置 | 根据动作类型动态显示参数表单 |
| 校验提示 | 实时校验，错误高亮显示 |
| 导入导出 | 支持导入/导出 JSON 任务定义 |
| 流程图 | 状态机任务显示状态转移图 |

### 4.3 前端组件结构

```typescript
interface TaskEditorProps {
  taskDefinition: TaskDefinition;
  resourcePackId: string;
  onSave: (definition: TaskDefinition) => void;
  onCancel: () => void;
}

interface StepEditorProps {
  step: StepInstruction;
  availableTemplates: string[];
  availableActions: ActionDefinition[];
  onChange: (step: StepInstruction) => void;
}

interface ParamsConfigEditorProps {
  paramsConfig: Record<string, ParamConfig>;
  onChange: (config: Record<string, ParamConfig>) => void;
}
```

---

## 5. 参数配置

### 5.1 参数类型

| 类型 | 说明 | UI 组件 | 示例 |
|------|------|---------|------|
| `string` | 字符串 | Input | 关卡名称 |
| `integer` | 整数 | InputNumber | 重复次数 |
| `float` | 浮点数 | InputNumber | 延迟时间 |
| `boolean` | 布尔值 | Switch | 是否使用药水 |
| `select` | 单选 | Select | 服务器选择 |

### 5.2 参数模板变量

任务节点中可通过 `{{param_name}}` 引用参数值：

```json
{
    "params_config": {
        "stage": {
            "type": "string",
            "default": "4-10",
            "label": "关卡"
        }
    },
    "nodes": [
        {
            "id": "select_stage",
            "name": "select_stage",
            "node_type": "template_match",
            "config": {
                "template": "stage_{{stage}}",
                "threshold": 0.8
            }
        }
    ]
}
```

### 5.3 参数解析

```python
import re

def resolve_params(step_params: dict, user_params: dict) -> dict:
    """解析步骤参数中的模板变量"""
    resolved = {}
    for key, value in step_params.items():
        if isinstance(value, str):
            resolved[key] = _resolve_template_vars(value, user_params)
        elif isinstance(value, dict):
            resolved[key] = resolve_params(value, user_params)
        else:
            resolved[key] = value
    return resolved

def _resolve_template_vars(template: str, params: dict) -> str:
    """替换模板变量 {{var}} 为实际值"""
    pattern = r"\{\{(\w+)\}\}"
    def replacer(match):
        var_name = match.group(1)
        return str(params.get(var_name, match.group(0)))
    return re.sub(pattern, replacer, template)
```

---

## 6. 与原生 Python 任务的统一展示

### 6.1 统一任务模型

自定义 JSON 任务和原生 Python 任务在 UI 中统一展示：

| 属性 | JSON 任务 | Python 任务 |
|------|----------|------------|
| 名称 | ✅ | ✅ |
| 描述 | ✅ | ✅ |
| 执行模式 | pipeline / state_machine | pipeline / state_machine |
| 参数配置 | params_config | auto_task 装饰器参数 |
| 节点列表 | nodes 数组 | Python auto_task 函数 (ChainManager 已废弃) |
| 可编辑 | ✅ 可视化编辑 | ❌ 只读展示 |
| 来源标记 | custom | native |

### 6.2 统一 API

```python
class TaskViewSet(viewsets.ModelViewSet):
    """任务统一 API"""

    def list(self, request):
        """列出所有任务（JSON + Python）"""
        native_tasks = self._get_native_tasks()
        custom_tasks = CustomTask.objects.all()
        combined = list(native_tasks) + list(custom_tasks)
        serializer = UnifiedTaskSerializer(combined, many=True)
        return Response(serializer.data)

    def _get_native_tasks(self):
        """获取原生 Python 任务"""
        return Task.objects.filter(source="native")

class UnifiedTaskSerializer:
    """统一任务序列化器"""

    def to_representation(self, instance):
        if isinstance(instance, CustomTask):
            return {
                "id": instance.id,
                "name": instance.name,
                "description": instance.description,
                "source": "custom",
                "editable": True,
                "execution_mode": "pipeline",
                "task_definition": instance.task_definition,
                "params_config": instance.params_config,
            }
        else:
            return {
                "id": instance.id,
                "name": instance.name,
                "description": instance.description,
                "source": "native",
                "editable": False,
                "execution_mode": instance.execution_mode,
                "task_definition": instance.task_definition,
                "params_config": instance.params_config,
            }
```

### 6.3 前端展示差异

| 展示项 | JSON 任务 | Python 任务 |
|--------|----------|------------|
| 任务列表 | 显示"自定义"标签 | 显示"原生"标签 |
| 详情页 | 可视化编辑器 | 步骤只读展示 |
| 参数配置 | 动态表单 | 固定参数 |
| 操作按钮 | 编辑/删除/复制 | 仅查看/执行 |
| 执行历史 | 统一展示 | 统一展示 |
