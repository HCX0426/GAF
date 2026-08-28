"""TD-060: Remove TraceSpan model from tasks app (state-only).

TraceSpan has been migrated to the tracing app (tracing migration 0001
creates tracing.TraceSpan with db_table='trace_span'). The physical
``trace_span`` table (56555 rows) is preserved — only the Django model
state is removed from the tasks app.

This is a SeparateDatabaseAndState migration:
- state_operations: DeleteModel('TraceSpan') — removes TraceSpan from
  tasks app's migration state.
- database_operations: [] — the physical table is NOT dropped; it is now
  owned by tracing.TraceSpan.

Dependencies:
- tasks.0039 (previous migration)
- (tracing.0001 will depend on this migration to avoid db_table clash)
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0039_remove_recording'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='TraceSpan'),
            ],
            database_operations=[],
        ),
    ]
