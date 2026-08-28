"""R37-P3 Stage 7 Task 20a: remove TaskChain + TaskChainNode from tasks app state.

Companion to pipeline/migrations/0002_taskchain.py. Together they move the
TaskChain and TaskChainNode models from the `tasks` app to the `pipeline`
app without touching the physical `tasks_taskchain` / `tasks_taskchainnode`
tables.

This migration is STATE-ONLY (SeparateDatabaseAndState with empty
database_operations): the physical tables stay in the DB and are now owned
by pipeline.TaskChain / pipeline.TaskChainNode (same db_table). Running
these DeleteModel operations only updates Django's migration state; it
does NOT drop the tables.

Dependency ordering: this migration depends on pipeline/0002_taskchain so
the receiving app's CreateModel runs first. Briefly both models exist in
both apps' state (harmless — Django does not enforce db_table uniqueness
across apps at migration time), then this migration removes them from
tasks. Net effect: the models are "moved" from tasks to pipeline.

Why pipeline is the right home:
- TaskChain defines DAG orchestration between tasks — a pipeline concept.
- TaskChainNode is a node in that DAG.
- The FK from TaskChainNode to tasks.Task is a legitimate cross-app
  reference (orchestrator depends on executor): pipeline -> tasks.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0031_remove_alertrule'),
        ('pipeline', '0002_taskchain'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name='TaskChain',
                ),
                migrations.DeleteModel(
                    name='TaskChainNode',
                ),
            ],
            database_operations=[],
        ),
    ]
