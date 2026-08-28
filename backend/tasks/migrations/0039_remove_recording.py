"""P-008: Remove Recording model from tasks app (state-only).

Recording has been migrated to the pipeline app (pipeline migration 0005
creates pipeline.Recording with db_table='recording'). The physical
``recording`` table (7 rows of user data) is preserved — only the Django
model state is removed from the tasks app.

This is a SeparateDatabaseAndState migration:
- state_operations: DeleteModel('Recording') — removes Recording from
  tasks app's migration state.
- database_operations: [] — the physical table is NOT dropped; it is now
  owned by pipeline.Recording.

Dependencies:
- tasks.0038 (previous migration)
- (pipeline.0005 will depend on this migration to avoid db_table clash)
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0038_remove_pipeline'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='Recording'),
            ],
            database_operations=[],
        ),
    ]
