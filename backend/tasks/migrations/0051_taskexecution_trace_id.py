"""B3-3 (spec 2026-07-30-debug-directory-restructure): TaskExecution 新增 trace_id 字段.

用于在 dispatch_task 时持久化 HTTP 请求级 trace_id (完整 UUID), 实现
HTTP → WS 帧 → backend log → agent log → meta.json 全链路 trace_id 贯穿.

字段约束:
- max_length=64: 容纳完整 UUID (36 字符) + 余量 (兼容未来可能的 trace_id 变体)
- blank=True, default='': 老数据 / CLI 触发的执行 / Celery 无请求上下文 兼容
- db_index=True: 便于按 trace_id 反查所有相关执行记录 (e.g. 排查一个 HTTP
  请求触发了哪些 task execution, 或一个 trace_id 关联了哪些 agent 执行)
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0050_executionstep_error_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="taskexecution",
            name="trace_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text=(
                    "B3-3 (spec 2026-07-30-debug-directory-restructure): HTTP 请求级 "
                    "trace_id (完整 UUID), 由 TracingMiddleware 注入到 ContextVar, "
                    "dispatch_task 时从 current_trace_id.get() 取. 全链路贯穿: "
                    "HTTP → WS 帧 → backend log → agent log → meta.json. "
                    "便于按 trace_id 反查所有相关执行记录."
                ),
                max_length=64,
                verbose_name="Trace ID",
            ),
        ),
    ]
