"""TD-061 Plan B Stage 2: remove tasks.Pipeline + tasks.PipelineSnapshot.

State-only operation (SeparateDatabaseAndState): the physical tables
``pipeline`` and ``pipeline_snapshot`` remain in the DB and are now owned by
the pipeline app (see pipeline migration 0004). FKs on TaskExecution.pipeline
and MarketplaceItem.pipeline are re-pointed in Django state only — the DB
FK constraint stays valid because pipeline.Pipeline's db_table becomes
'pipeline' in the same migrate run (pipeline 0004 runs immediately after
this migration via the explicit dependency).

Why state-only:
- Dropping the ``pipeline`` table would lose 5 real user rows + break 26
  TaskExecution.pipeline_id references. Plan B keeps the table and transfers
  ownership to the pipeline app instead.
- Re-pointing the FK at the DB level would make SQLite recreate
  tasks_taskexecution with a new FK constraint to pipeline_pipeline(id) —
  wrong target. Keeping the DB untouched preserves the existing constraint
  to pipeline(id), which becomes correct once pipeline 0004 swaps
  pipeline.Pipeline's db_table to 'pipeline'.

Order within migration:
1. AlterField TaskExecution.pipeline → to='pipeline.Pipeline'
2. AlterField MarketplaceItem.pipeline → to='pipeline.Pipeline'
3. DeleteModel tasks.PipelineSnapshot (removes its FK to tasks.Pipeline)
4. DeleteModel tasks.Pipeline (self-FK + remaining inbound FKs removed)
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0037_remove_gameprofile'),
        ('pipeline', '0003_pipeline_sub_pipeline_pipeline_user'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # 1. Re-point TaskExecution.pipeline FK to pipeline.Pipeline
                #    BEFORE removing tasks.Pipeline (so FK target stays valid).
                migrations.AlterField(
                    model_name='taskexecution',
                    name='pipeline',
                    field=models.ForeignKey(
                        blank=True,
                        help_text='Pipeline 执行时关联的 Pipeline 记录（链式任务执行时为空）',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='executions',
                        to='pipeline.Pipeline',
                        verbose_name='关联 Pipeline',
                    ),
                ),
                # 2. Re-point MarketplaceItem.pipeline FK to pipeline.Pipeline.
                migrations.AlterField(
                    model_name='marketplaceitem',
                    name='pipeline',
                    field=models.ForeignKey(
                        blank=True,
                        help_text='关联的 Pipeline 记录',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='market_items',
                        to='pipeline.Pipeline',
                        verbose_name='关联Pipeline',
                    ),
                ),
                # 3. Remove tasks.PipelineSnapshot (FK to tasks.Pipeline removed with it).
                migrations.DeleteModel(name='PipelineSnapshot'),
                # 4. Remove tasks.Pipeline (self-FK + any remaining inbound FKs gone).
                migrations.DeleteModel(name='Pipeline'),
            ],
            database_operations=[
                # Intentionally empty: ``pipeline`` and ``pipeline_snapshot``
                # tables stay in DB — ownership transfers to pipeline app via
                # migration 0004 (which only adds columns + drops orphaned
                # pipeline_pipeline / pipeline_version_snapshot tables).
            ],
        ),
    ]
