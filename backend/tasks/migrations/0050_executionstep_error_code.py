"""Task 3.6 (P2-6): ExecutionStep 新增 error_code 字段。

用于在 WS broadcast_execution_step_update 时透传 agent AutoResult.error_code
给前端, 前端按 error.codes.<CODE> 映射多语言, 而非把后端 businessMessage (中文)
原文甩给多语言用户 (N192 B1/B2 视角: 错误提示归一 + 错误码映射)。

字段约束:
- max_length=64: 容纳 NO_MATCH / LOW_CONFIDENCE / SCREEN_TIMEOUT 等枚举
- blank=True, default='': 老数据 / 成功步骤 / agent 未上报 error_code 兼容
- 不加 db_index: 查询频率低, 按 task_result + step_index 索引已足够
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0049_chain_to_pipeline_unification"),
    ]

    operations = [
        migrations.AddField(
            model_name="executionstep",
            name="error_code",
            field=models.CharField(
                blank=True,
                default="",
                help_text="节点级错误码 (NO_MATCH/LOW_CONFIDENCE/TIMEOUT/...), 与 agent AutoResult.error_code 对齐",
                max_length=64,
                verbose_name="错误码",
            ),
        ),
    ]
