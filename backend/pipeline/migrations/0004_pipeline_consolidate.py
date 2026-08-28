"""TD-061 Plan B Stage 2: consolidate pipeline.Pipeline to physical table ``pipeline``.

This migration completes the consolidation started in Stage 1. Combined with
tasks migration 0038 (state-only removal of tasks.Pipeline + tasks.PipelineSnapshot
and FK re-pointing), pipeline.Pipeline becomes the canonical model owning the
``pipeline`` and ``pipeline_snapshot`` physical tables.

State operations (DeleteModel + CreateModel replaces the model definition):
- Pipeline:
  * PK UUIDField → BigAutoField (matches existing ``pipeline.id`` INTEGER PK)
  * db_table 'pipeline_pipeline' → 'pipeline' (接管 tasks.Pipeline's table)
  * graph_data: add db_column='pipeline_data' (bridges to existing column)
  * name: max_length 200 → 255 (matches existing varchar(255))
  * description: add default='' (matches tasks.Pipeline schema)
  * user: drop null/blank (matches NOT NULL user_id column), revert
    related_name to 'pipelines' (tasks.Pipeline gone)
  * sub_pipeline: change related_name to 'used_by_pipelines' (matches tasks.Pipeline)
- PipelineSnapshot:
  * db_table 'pipeline_version_snapshot' → 'pipeline_snapshot'
  * graph_data: add db_column='pipeline_data', drop default (matches NOT NULL
    column with no default)
  * change_summary: TextField → CharField(500), add db_column='comment'
    (matches existing varchar(500) column)
  * Drop unique_together (physical table lacks the constraint)

Database operations:
- ALTER TABLE pipeline ADD COLUMN is_template bool NOT NULL DEFAULT 0
  (5 existing rows get is_template=False; new field not in tasks.Pipeline schema)
- ALTER TABLE pipeline ADD COLUMN estimated_duration_ms integer NOT NULL DEFAULT 0
  (same reasoning)
- DROP TABLE pipeline_pipeline (orphaned; 4 rows of E2E test data — acceptable
  loss per Plan B decision memo §5.1)
- DROP TABLE pipeline_version_snapshot (orphaned; 0 rows)

Dependency on tasks.0038: pipeline.Pipeline's new db_table='pipeline' would
clash with tasks.Pipeline's db_table='pipeline' if both models existed in
state. tasks 0038 removes tasks.Pipeline first, so this migration must run
after it.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pipeline', '0003_pipeline_sub_pipeline_pipeline_user'),
        ('tasks', '0038_remove_pipeline'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # Remove old Pipeline + PipelineSnapshot state (db_table
                # 'pipeline_pipeline' / 'pipeline_version_snapshot', UUIDField PK,
                # no db_column bridging).
                migrations.DeleteModel(name='Pipeline'),
                migrations.DeleteModel(name='PipelineSnapshot'),
                # Re-create Pipeline with target schema (db_table='pipeline',
                # BigAutoField PK, db_column bridges, related_name reverted).
                migrations.CreateModel(
                    name='Pipeline',
                    fields=[
                        ('id', models.BigAutoField(
                            auto_created=True, primary_key=True,
                            serialize=False, verbose_name='ID',
                        )),
                        ('name', models.CharField(
                            max_length=255, verbose_name='Pipeline 名称',
                        )),
                        ('description', models.TextField(
                            blank=True, default='', verbose_name='描述',
                        )),
                        ('graph_data', models.JSONField(
                            default=dict, verbose_name='画布数据',
                            db_column='pipeline_data',
                        )),
                        ('version', models.IntegerField(
                            default=1, verbose_name='版本号',
                        )),
                        ('is_template', models.BooleanField(
                            default=False, verbose_name='是否为快速模板',
                        )),
                        ('estimated_duration_ms', models.IntegerField(
                            default=0, verbose_name='预估耗时(ms)',
                        )),
                        ('created_at', models.DateTimeField(
                            auto_now_add=True, verbose_name='创建时间',
                        )),
                        ('updated_at', models.DateTimeField(
                            auto_now=True, verbose_name='更新时间',
                        )),
                        ('user', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='pipelines',
                            to=settings.AUTH_USER_MODEL,
                            verbose_name='所属用户',
                        )),
                        ('sub_pipeline', models.ForeignKey(
                            blank=True, null=True,
                            on_delete=django.db.models.deletion.SET_NULL,
                            related_name='used_by_pipelines',
                            to='pipeline.pipeline',
                            verbose_name='子流水线',
                        )),
                    ],
                    options={
                        'verbose_name': 'Pipeline',
                        'verbose_name_plural': 'Pipeline',
                        'db_table': 'pipeline',
                        'ordering': ['-updated_at'],
                    },
                ),
                # Re-create PipelineSnapshot with target schema
                # (db_table='pipeline_snapshot', db_column bridges,
                # CharField(500) change_summary).
                migrations.CreateModel(
                    name='PipelineSnapshot',
                    fields=[
                        ('id', models.BigAutoField(
                            auto_created=True, primary_key=True,
                            serialize=False, verbose_name='ID',
                        )),
                        ('version', models.IntegerField(
                            verbose_name='快照版本号',
                        )),
                        ('graph_data', models.JSONField(
                            verbose_name='画布数据快照',
                            db_column='pipeline_data',
                        )),
                        ('change_summary', models.CharField(
                            blank=True, default='', max_length=500,
                            verbose_name='变更摘要',
                            db_column='comment',
                        )),
                        ('created_at', models.DateTimeField(
                            auto_now_add=True, verbose_name='创建时间',
                        )),
                        ('pipeline', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='snapshots',
                            to='pipeline.pipeline',
                            verbose_name='关联 Pipeline',
                        )),
                    ],
                    options={
                        'verbose_name': 'Pipeline 版本快照',
                        'verbose_name_plural': 'Pipeline 版本快照',
                        'db_table': 'pipeline_snapshot',
                        'ordering': ['-version'],
                    },
                ),
            ],
            database_operations=[
                # Add new columns to ``pipeline`` table (NOT in tasks.Pipeline
                # schema, so the existing physical table lacks them). Existing
                # 5 rows get default values (is_template=False, estimated_duration_ms=0).
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE pipeline "
                        "ADD COLUMN is_template bool NOT NULL DEFAULT 0;"
                    ),
                    reverse_sql="ALTER TABLE pipeline DROP COLUMN is_template;",
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE pipeline "
                        "ADD COLUMN estimated_duration_ms integer NOT NULL DEFAULT 0;"
                    ),
                    reverse_sql="ALTER TABLE pipeline DROP COLUMN estimated_duration_ms;",
                ),
                # Drop orphaned tables. pipeline_pipeline held 4 E2E test rows
                # (acceptable loss per Plan B); pipeline_version_snapshot was empty.
                # No reverse_sql — data is gone and tables are re-created by
                # rolling back the CreateModel in state_operations (which won't
                # actually re-create the DB table, but that's fine because the
                # state-only reverse would re-point the model back to the dropped
                # table, which is the pre-migration state).
                migrations.RunSQL(
                    sql="DROP TABLE IF EXISTS pipeline_pipeline;",
                    reverse_sql="",
                ),
                migrations.RunSQL(
                    sql="DROP TABLE IF EXISTS pipeline_version_snapshot;",
                    reverse_sql="",
                ),
            ],
        ),
    ]
