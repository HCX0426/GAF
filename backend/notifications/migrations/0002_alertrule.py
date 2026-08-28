"""R37-P3 Stage 7 Task 20a: migrate AlertRule from tasks to notifications.

This is a STATE-ONLY migration (SeparateDatabaseAndState with empty
database_operations). The physical table `alert_rule` stays where it is —
we only move the Django model definition from the `tasks` app to the
`notifications` app.

Why state-only:
- The `alert_rule` table already exists (created by
  tasks/migrations/0009_alertrule_notification_slametric_webhook.py).
- AlertRule had 0 rows at inventory time (Stage 7盘点), so even a data
  migration would be trivial — but state-only is the zero-risk pattern.
- db_table stays 'alert_rule' so all existing rows (if any) keep working.

The companion migration tasks/0031_remove_alertrule.py deletes AlertRule
from the tasks app state with the same SeparateDatabaseAndState pattern.
Running both together makes Django's migration state agree that AlertRule
now belongs to notifications, while the DB is untouched.

Note: related_name changed from 'task_alert_rules' to 'alert_rules' to
reflect the new home app. This is a Python-level reverse accessor change
(not stored in the DB), and a codebase grep confirmed no code uses
`user.task_alert_rules`, so the rename is safe.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='AlertRule',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(max_length=100, verbose_name='规则名称', help_text='告警规则的名称')),
                        ('rule_type', models.CharField(max_length=50, verbose_name='规则类型', help_text='告警规则的类型标识')),
                        ('threshold', models.IntegerField(default=3, verbose_name='阈值', help_text='触发告警的阈值')),
                        ('enabled', models.BooleanField(default=True, verbose_name='已启用', help_text='标记规则是否启用')),
                        ('quiet_start', models.TimeField(blank=True, help_text='静默时段的开始时间', null=True, verbose_name='静默开始')),
                        ('quiet_end', models.TimeField(blank=True, help_text='静默时段的结束时间', null=True, verbose_name='静默结束')),
                        ('notify_methods', models.JSONField(default=list, verbose_name='通知方式', help_text='告警触发的通知方式列表')),
                        ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间', help_text='记录创建的时间戳')),
                        ('user', models.ForeignKey(help_text='规则所属的用户', on_delete=django.db.models.deletion.CASCADE, related_name='alert_rules', to=settings.AUTH_USER_MODEL, verbose_name='用户')),
                    ],
                    options={
                        'verbose_name': '告警规则',
                        'verbose_name_plural': '告警规则',
                        'db_table': 'alert_rule',
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
