"""R37-P3 Stage 7 Task 20a: remove TemplateEffectiveness from tasks app state.

Companion to resources/migrations/0008_templateeffectiveness.py. Together
they move the TemplateEffectiveness model from the `tasks` app to the
`resources` app without touching the physical `tasks_templateeffectiveness`
table.

This migration is STATE-ONLY (SeparateDatabaseAndState with empty
database_operations): the physical table stays in the DB and is now owned
by resources.TemplateEffectiveness (same db_table). Running this DeleteModel
only updates Django's migration state; it does NOT drop the table.

Dependency ordering: this migration depends on resources/0008_templateeffectiveness
so the receiving app's CreateModel runs first. Briefly TemplateEffectiveness
exists in both apps' state (harmless — Django does not enforce db_table
uniqueness across apps at migration time), then this migration removes it
from tasks. Net effect: the model is "moved" from tasks to resources.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0033_remove_featureflag'),
        ('resources', '0008_templateeffectiveness'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name='TemplateEffectiveness',
                ),
            ],
            database_operations=[],
        ),
    ]
