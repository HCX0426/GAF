"""R37-P3 Stage 7 Task 20a: migrate FeatureFlag from tasks to settings.

STATE-ONLY migration (SeparateDatabaseAndState with empty database_operations).
The physical table `feature_flag` stays where it is — we only move the Django
model definition from the `tasks` app to the `settings` app.

Why settings is the right home:
- FeatureFlag controls global feature toggles (enable/disable, rollout %,
  role/IP whitelists) — a system-wide configuration concern, not a task
  execution concern.
- The settings app already owns UnattendedStrategy and LLMConfig (other
  system-wide configuration models). FeatureFlag fits naturally alongside.

Companion migration tasks/0033_remove_featureflag deletes the model from
tasks state and depends on THIS migration, so the model is "moved" (briefly
in both apps, then only in settings).

db_table kept as 'feature_flag' — zero data migration. The table has 0 rows.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0002_llmconfig'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='FeatureFlag',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(help_text='功能开关的唯一名称', max_length=255, unique=True, verbose_name='功能名称')),
                        ('description', models.TextField(blank=True, default='', help_text='功能开关的说明描述', verbose_name='描述')),
                        ('enabled', models.BooleanField(default=True, help_text='标记功能是否全局启用', verbose_name='是否启用')),
                        ('rollout_percentage', models.IntegerField(default=100, help_text='灰度发布的百分比, 0-100', verbose_name='灰度百分比 (0-100)')),
                        ('allowed_roles', models.JSONField(blank=True, default=list, help_text='允许使用该功能的角色列表', verbose_name='允许的角色列表')),
                        ('allowed_ips', models.JSONField(blank=True, default=list, help_text='允许使用该功能的 IP 白名单', verbose_name='允许的 IP 列表')),
                        ('created_at', models.DateTimeField(auto_now_add=True, help_text='记录创建的时间戳', verbose_name='创建时间')),
                        ('updated_at', models.DateTimeField(auto_now=True, help_text='记录最近一次更新的时间戳', verbose_name='更新时间')),
                    ],
                    options={
                        'verbose_name': '功能开关',
                        'verbose_name_plural': '功能开关',
                        'db_table': 'feature_flag',
                        'ordering': ['name'],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
