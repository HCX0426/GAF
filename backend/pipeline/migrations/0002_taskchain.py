"""R37-P3 Stage 7 Task 20a: migrate TaskChain + TaskChainNode from tasks to pipeline.

STATE-ONLY migration (SeparateDatabaseAndState with empty database_operations).
The physical tables `tasks_taskchain` and `tasks_taskchainnode` stay where they
are — we only move the Django model definitions from the `tasks` app to the
`pipeline` app.

Why pipeline is the right home:
- TaskChain defines DAG orchestration between tasks — a pipeline concept.
- TaskChainNode is a node in that DAG.
- The FK from TaskChainNode to tasks.Task is a legitimate cross-app reference
  (orchestrator depends on executor): pipeline → tasks.

Dependency on tasks/0031 ensures tasks.Task exists in migration state when
pipeline.TaskChainNode (FK to 'tasks.Task') is created. The companion migration
tasks/0032_remove_taskchain deletes both models from tasks state and depends
on THIS migration, so the model is "moved" (briefly in both apps, then only
in pipeline).

db_table kept as 'tasks_taskchain' / 'tasks_taskchainnode' — zero data migration.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pipeline', '0001_initial'),
        ('tasks', '0031_remove_alertrule'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='TaskChain',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(help_text='任务链的显示名称', max_length=255, verbose_name='任务链名称')),
                        ('description', models.TextField(blank=True, default='', help_text='任务链的详细描述', verbose_name='描述')),
                        ('dag_data', models.JSONField(default=dict, help_text='任务链的 DAG 节点和边数据', verbose_name='DAG 图数据 (React Flow nodes + edges)')),
                        ('is_enabled', models.BooleanField(default=True, help_text='标记任务链是否处于启用状态', verbose_name='是否启用')),
                        ('created_at', models.DateTimeField(auto_now_add=True, help_text='记录创建的时间戳', verbose_name='创建时间')),
                        ('updated_at', models.DateTimeField(auto_now=True, help_text='记录最近一次更新的时间戳', verbose_name='更新时间')),
                        ('created_by', models.ForeignKey(help_text='创建该任务链的用户', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_chains', to=settings.AUTH_USER_MODEL, verbose_name='创建者')),
                    ],
                    options={
                        'verbose_name': '任务链',
                        'verbose_name_plural': '任务链',
                        'db_table': 'tasks_taskchain',
                        'ordering': ['-created_at'],
                    },
                ),
                migrations.CreateModel(
                    name='TaskChainNode',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('condition', models.JSONField(blank=True, default=dict, help_text='节点执行的条件配置', verbose_name='条件配置')),
                        ('order', models.IntegerField(help_text='节点在链中的执行顺序', verbose_name='排序')),
                        ('chain', models.ForeignKey(blank=True, help_text='节点所属的任务链', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='chain_nodes', to='pipeline.TaskChain', verbose_name='关联任务链')),
                        ('parent', models.ForeignKey(blank=True, help_text='父节点, 用于构建 DAG 结构', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='pipeline.TaskChainNode', verbose_name='父节点')),
                        ('task', models.ForeignKey(help_text='节点关联的任务记录', on_delete=django.db.models.deletion.CASCADE, related_name='chain_nodes', to='tasks.Task', verbose_name='关联任务')),
                    ],
                    options={
                        'verbose_name': '任务链节点',
                        'verbose_name_plural': '任务链节点',
                        'db_table': 'tasks_taskchainnode',
                        'ordering': ['order'],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
