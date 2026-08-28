"""Pipeline execution tracking — allow TaskExecution without Task, add pipeline FK.

This unblocks Pipeline executions being tracked in TaskExecution table.
Previously PipelineViewSet.execute sent WS messages but never created a
TaskExecution record, so progress/completion were silently lost.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0024_alter_alertrule_quiet_end_and_more'),
    ]

    operations = [
        # Make task nullable so Pipeline executions (which have no parent Task)
        # can still create a TaskExecution row.
        migrations.AlterField(
            model_name='taskexecution',
            name='task',
            field=models.ForeignKey(
                blank=True,
                help_text='关联的任务记录（Pipeline 执行时可为空，改用 pipeline 字段）',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='executions',
                to='tasks.task',
                verbose_name='关联任务',
            ),
        ),
        # Add pipeline FK so Pipeline executions can be traced back to their
        # Pipeline definition.
        migrations.AddField(
            model_name='taskexecution',
            name='pipeline',
            field=models.ForeignKey(
                blank=True,
                help_text='Pipeline 执行时关联的 Pipeline 记录（链式任务执行时为空）',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='executions',
                to='tasks.pipeline',
                verbose_name='关联 Pipeline',
            ),
        ),
    ]
