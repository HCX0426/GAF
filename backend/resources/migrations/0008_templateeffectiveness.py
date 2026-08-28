"""R37-P3 Stage 7 Task 20a: migrate TemplateEffectiveness from tasks to resources.

STATE-ONLY migration (SeparateDatabaseAndState with empty database_operations).
The physical table `tasks_templateeffectiveness` stays where it is — we only
move the Django model definition from the `tasks` app to the `resources` app.

Why resources is the right home:
- TemplateEffectiveness is per-template metadata keyed on resources.Template.
  In the tasks app the FK crossed app boundaries (tasks.TemplateEffectiveness
  -> resources.Template); moving it here makes the FK intra-app and lets the
  resources app own the full template lifecycle (definition, versions,
  annotations, effectiveness).
- The companion view template_references_view lived in resources.views but had
  to `from tasks.models import TemplateEffectiveness` — that cross-app import
  is eliminated.

Companion migration tasks/0034_remove_templateeffectiveness deletes the model
from tasks state and depends on THIS migration, so the model is "moved"
(briefly in both apps, then only in resources).

db_table kept as 'tasks_templateeffectiveness' — zero data migration. The
table has 0 rows.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0007_r37_p1_game_profile_fk'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='TemplateEffectiveness',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('template_name', models.CharField(default='', help_text='模板的显示名称', max_length=255, verbose_name='模板名称')),
                        ('total_attempts', models.IntegerField(default=0, help_text='模板累计匹配尝试次数', verbose_name='总尝试次数')),
                        ('success_count', models.IntegerField(default=0, help_text='模板匹配成功次数', verbose_name='成功次数')),
                        ('fail_count', models.IntegerField(default=0, help_text='模板匹配失败次数', verbose_name='失败次数')),
                        ('last_success_at', models.DateTimeField(blank=True, help_text='模板最近一次匹配成功的时间', null=True, verbose_name='最后成功时间')),
                        ('last_match_time', models.DateTimeField(blank=True, help_text='模板最近一次被使用的时间', null=True, verbose_name='最后匹配时间')),
                        ('avg_confidence', models.FloatField(default=0, help_text='模板匹配的平均置信度', verbose_name='平均置信度')),
                        ('consecutive_failures', models.IntegerField(default=0, help_text='模板连续匹配失败次数', verbose_name='连续失败次数')),
                        ('is_suspected_invalid', models.BooleanField(default=False, help_text='标记模板是否疑似失效', verbose_name='疑似无效')),
                        ('created_at', models.DateTimeField(auto_now_add=True, help_text='记录创建的时间戳', verbose_name='创建时间')),
                        ('updated_at', models.DateTimeField(auto_now=True, help_text='记录最近一次更新的时间戳', verbose_name='更新时间')),
                        ('template', models.ForeignKey(help_text='关联的模板记录', on_delete=models.deletion.CASCADE, related_name='effectiveness_records', to='resources.template', verbose_name='关联模板')),
                    ],
                    options={
                        'verbose_name': '模板有效性',
                        'verbose_name_plural': '模板有效性',
                        'db_table': 'tasks_templateeffectiveness',
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
