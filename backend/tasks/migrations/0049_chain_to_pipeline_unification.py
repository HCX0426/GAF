"""spec-2026-07-27-execution-path-unification 阶段 5: chain → pipeline 归一化.

1. 改 Task.execution_mode choices: 移除 CHAIN, 新增 PIPELINE
2. 数据迁移: 把 execution_mode='chain' 的 Task 改为 'pipeline'
3. 数据迁移: 把 task_definition 是 chain schema 的转成 pipeline schema

chain → pipeline schema 转换规则:
  {"steps": [{"name": "x", "action": "click", "params": {...}, ...}]}
  →
  {"nodes": [{"id": "x", "node_type": "click", "config": {...}, ...}]}
  (无 edges → PipelineParser 线性模式自动按顺序链接)
"""
from django.db import migrations, models


def chain_to_pipeline_task_definition(task_definition):
    """把 chain schema task_definition 转成 pipeline schema.

    检测逻辑: 如果有 "steps" 字段且无 "nodes" 字段, 视为 chain schema.
    其他情况 (已有 nodes / 空 dict / state_machine module) 原样返回.
    """
    if not isinstance(task_definition, dict):
        return task_definition

    # 已是 pipeline schema 或 state_machine schema → 不动
    if "nodes" in task_definition or "module" in task_definition:
        return task_definition

    steps = task_definition.get("steps")
    if not isinstance(steps, list) or not steps:
        return task_definition

    nodes = []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        node = {
            "id": step.get("name") or f"step_{idx}",
            "node_type": step.get("action", ""),
            "config": step.get("params", {}),
        }
        # 透传 chain step 的节点内控制流字段（PipelineNode 已支持）
        for field in ("pre_verify", "post_verify", "retry", "fallback",
                      "comment", "rationale"):
            val = step.get(field)
            if val:
                node[field] = val
        if step.get("continue_on_error"):
            node["continue_on_error"] = True
        nodes.append(node)

    return {"nodes": nodes}


def migrate_chain_to_pipeline(apps, schema_editor):
    """数据迁移: chain → pipeline."""
    Task = apps.get_model("tasks", "Task")
    # 1. execution_mode: 'chain' → 'pipeline'
    Task.objects.filter(execution_mode="chain").update(execution_mode="pipeline")
    # 2. task_definition: chain schema → pipeline schema
    for task in Task.objects.filter(execution_mode="pipeline").iterator():
        new_def = chain_to_pipeline_task_definition(task.task_definition)
        if new_def != task.task_definition:
            task.task_definition = new_def
            task.save(update_fields=["task_definition"])


def reverse_migrate_pipeline_to_chain(apps, schema_editor):
    """反向迁移: 不做转换 (chain schema 已废弃, 回滚后 task_definition 仍是 pipeline).

    execution_mode 'pipeline' 在旧代码里不被识别, 但旧代码默认按 chain 处理,
    所以 task_definition 是 pipeline schema 时旧 chain 执行器会失败.
    这是预期行为 — 归一化是不可逆的架构变更.
    """
    Task = apps.get_model("tasks", "Task")
    Task.objects.filter(execution_mode="pipeline").update(execution_mode="chain")


class Migration(migrations.Migration):
    """spec-2026-07-27-execution-path-unification 阶段 5."""

    dependencies = [
        ("tasks", "0048_taskexec_composite_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="task",
            name="execution_mode",
            field=models.CharField(
                choices=[("pipeline", "Pipeline"), ("state_machine", "State Machine")],
                default="pipeline",
                help_text="执行模式: pipeline/state_machine (chain 已废弃，归一化到 pipeline)",
                max_length=20,
                verbose_name="执行模式",
            ),
        ),
        migrations.RunPython(migrate_chain_to_pipeline, reverse_migrate_pipeline_to_chain),
    ]
