"""R37-P3 Stage 7 Task 20a: migrate AuditLog from tasks to accounts.

STATE-ONLY migration (SeparateDatabaseAndState with empty database_operations).
The physical table `audit_log` stays where it is — we only move the Django
model definition from the `tasks` app to the `accounts` app.

Why accounts is the right home:
- AuditLog records user actions (login/logout/create/update/delete/...) keyed
  on settings.AUTH_USER_MODEL. In the tasks app the FK crossed app boundaries
  (tasks.AuditLog -> accounts.User); moving it here makes the FK intra-app.
- accounts/admin.py already registered AuditLog via a cross-app import
  (`from tasks.models import AuditLog`); moving the model here turns that
  into a same-app reference and eliminates the reverse dependency
  (accounts -> tasks).
- core/views.py (LogCenter union query) and tasks/audit.py (log_audit writer)
  also import AuditLog from tasks; after this move they import from accounts.
  log_audit itself moves to accounts/audit.py so the audit writer lives with
  the audit model.

Companion migration tasks/0035_remove_auditlog deletes the model from tasks
state and depends on THIS migration, so the model is "moved" (briefly in both
apps, then only in accounts).

db_table kept as 'audit_log' — zero data migration. The table has 0 rows
(log_audit writer is currently uncalled — dead code path).
related_name kept as 'task_audit_logs' to avoid reverse-relation name churn
on User; a follow-up could rename it to 'audit_logs' once callers are
audited.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_r37_p1_game_profile_fk'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='AuditLog',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('action', models.CharField(choices=[('login', '登录'), ('logout', '登出'), ('create', '创建'), ('update', '更新'), ('delete', '删除'), ('execute', '执行'), ('import', '导入'), ('export', '导出')], help_text='操作: login/logout/create/update/delete/execute/import/export', max_length=20, verbose_name='操作')),
                        ('resource_type', models.CharField(help_text='被操作资源的类型', max_length=100, verbose_name='资源类型')),
                        ('resource_id', models.CharField(blank=True, default='', help_text='被操作资源的标识', max_length=255, verbose_name='资源ID')),
                        ('details', models.JSONField(default=dict, help_text='操作的详细信息', verbose_name='详情')),
                        ('ip_address', models.GenericIPAddressField(blank=True, help_text='操作发起的 IP 地址', null=True, verbose_name='IP地址')),
                        ('created_at', models.DateTimeField(auto_now_add=True, help_text='操作发生的时间', verbose_name='操作时间')),
                        ('user', models.ForeignKey(help_text='执行操作的用户', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_audit_logs', to=settings.AUTH_USER_MODEL, verbose_name='用户')),
                    ],
                    options={
                        'verbose_name': '审计日志',
                        'verbose_name_plural': '审计日志',
                        'db_table': 'audit_log',
                        'ordering': ['-created_at'],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
