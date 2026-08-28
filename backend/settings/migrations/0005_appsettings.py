"""R37-P3 Stage 7 Task 20b: migrate AppSettings from tasks to settings.

STATE-ONLY migration (SeparateDatabaseAndState with empty database_operations).
The physical table `tasks_appsettings` stays where it is — we only move the
Django model definition from the `tasks` app to the `settings` app.

Why settings is the right home:
- AppSettings is a system-wide key/value configuration store (register toggle,
  device_config, llm_config, OCR engine config, ...). It is NOT a task-execution
  concern — it just happened to be born in the tasks app.
- The settings app already owns UnattendedStrategy, LLMConfig and FeatureFlag
  (the other system-wide configuration models). AppSettings fits naturally
  alongside them.
- accounts/views.py had three cross-app imports
  (`from tasks.models import AppSettings`) for the register toggle and the
  initial-setup device_config. Moving AppSettings here turns those into same-app
  references (accounts -> settings is still cross-app, but the import is now
  semantically correct: accounts reads system settings, not task data). The
  reverse dependency (accounts -> tasks) is eliminated.

Companion migration tasks/0036_remove_appsettings deletes the model from tasks
state and depends on THIS migration, so the model is "moved" (briefly in both
apps, then only in settings).

db_table kept as 'tasks_appsettings' — zero data migration. The table has 1 row
(device_config from initial setup).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0004_alter_llmconfig_api_base_alter_llmconfig_api_key_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='AppSettings',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('setting_key', models.CharField(help_text='配置项的唯一键名', max_length=255, unique=True, verbose_name='配置键')),
                        ('setting_value', models.JSONField(default=dict, help_text='配置项的值', verbose_name='配置值')),
                        ('category', models.CharField(default='general', help_text='配置项所属分类', max_length=100, verbose_name='配置分类')),
                        ('description', models.CharField(blank=True, help_text='配置项的说明描述', max_length=512, verbose_name='配置说明')),
                        ('created_at', models.DateTimeField(auto_now_add=True, help_text='记录创建的时间戳', verbose_name='创建时间')),
                        ('updated_at', models.DateTimeField(auto_now=True, help_text='记录最近一次更新的时间戳', verbose_name='更新时间')),
                        ('updated_by', models.ForeignKey(blank=True, help_text='最近更新该配置的用户', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='更新者')),
                    ],
                    options={
                        'verbose_name': '应用设置',
                        'verbose_name_plural': '应用设置',
                        'db_table': 'tasks_appsettings',
                        'ordering': ['category', 'setting_key'],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
