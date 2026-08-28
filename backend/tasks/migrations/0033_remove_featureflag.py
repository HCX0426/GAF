"""R37-P3 Stage 7 Task 20a: remove FeatureFlag from tasks app state.

Companion to settings/migrations/0003_featureflag.py. Together they move
the FeatureFlag model from the `tasks` app to the `settings` app without
touching the physical `feature_flag` table.

This migration is STATE-ONLY (SeparateDatabaseAndState with empty
database_operations): the physical table stays in the DB and is now owned
by settings.FeatureFlag (same db_table). Running this DeleteModel only
updates Django's migration state; it does NOT drop the table.

Dependency ordering: this migration depends on settings/0003_featureflag
so the receiving app's CreateModel runs first. Briefly FeatureFlag exists
in both apps' state (harmless — Django does not enforce db_table
uniqueness across apps at migration time), then this migration removes
it from tasks. Net effect: the model is "moved" from tasks to settings.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0032_remove_taskchain'),
        ('settings', '0003_featureflag'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name='FeatureFlag',
                ),
            ],
            database_operations=[],
        ),
    ]
