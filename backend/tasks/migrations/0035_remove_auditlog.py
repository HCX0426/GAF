"""R37-P3 Stage 7 Task 20a: remove AuditLog from tasks app state.

Companion to accounts/migrations/0014_auditlog.py. Together they move the
AuditLog model from the `tasks` app to the `accounts` app without touching
the physical `audit_log` table.

This migration is STATE-ONLY (SeparateDatabaseAndState with empty
database_operations): the physical table stays in the DB and is now owned
by accounts.AuditLog (same db_table). Running this DeleteModel only updates
Django's migration state; it does NOT drop the table.

Dependency ordering: this migration depends on accounts/0014_auditlog so the
receiving app's CreateModel runs first. Briefly AuditLog exists in both apps'
state (harmless — Django does not enforce db_table uniqueness across apps at
migration time), then this migration removes it from tasks. Net effect: the
model is "moved" from tasks to accounts.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0034_remove_templateeffectiveness'),
        ('accounts', '0014_auditlog'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name='AuditLog',
                ),
            ],
            database_operations=[],
        ),
    ]
