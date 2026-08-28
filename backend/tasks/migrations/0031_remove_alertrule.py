"""R37-P3 Stage 7 Task 20a: remove AlertRule from tasks app state.

Companion to notifications/migrations/0002_alertrule.py. Together they
move the AlertRule model from the `tasks` app to the `notifications` app
without touching the physical `alert_rule` table.

This migration is STATE-ONLY (SeparateDatabaseAndState with empty
database_operations): the `alert_rule` table stays in the DB and is now
owned by notifications.AlertRule (same db_table). Running this DeleteModel
only updates Django's migration state; it does NOT drop the table.

Dependency ordering: this migration depends on notifications/0002_alertrule
so the receiving app's CreateModel runs first. Briefly AlertRule exists in
both apps' state (harmless — Django does not enforce db_table uniqueness
across apps at migration time), then this migration removes it from tasks.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0030_remove_recovery_config'),
        ('notifications', '0002_alertrule'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name='AlertRule',
                ),
            ],
            database_operations=[],
        ),
    ]
