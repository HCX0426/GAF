"""P-008: Add Recording model to pipeline app (state-only).

Recording has been migrated from the tasks app. The physical ``recording``
table (7 rows of user data) already exists and is preserved — only the
Django model state is created in the pipeline app.

This is a SeparateDatabaseAndState migration:
- state_operations: CreateModel('Recording') with db_table='recording' —
  adds Recording to pipeline app's migration state.
- database_operations: [] — the physical table already exists (created by
  tasks app's initial migration); no DDL needed.

Dependency on tasks.0039: pipeline.Recording's db_table='recording' would
clash with tasks.Recording's db_table='recording' if both models existed in
state. tasks 0039 removes tasks.Recording first, so this migration must run
after it.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pipeline', '0004_pipeline_consolidate'),
        ('tasks', '0039_remove_recording'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Recording',
                    fields=[
                        ('id', models.BigAutoField(
                            auto_created=True, primary_key=True,
                            serialize=False, verbose_name='ID',
                        )),
                        ('name', models.CharField(
                            max_length=255, verbose_name='名称',
                            help_text='录制的显示名称',
                        )),
                        ('recording_data', models.JSONField(
                            default=dict, verbose_name='录制数据JSON',
                            help_text='录制的原始数据 JSON',
                        )),
                        ('pipeline_json', models.JSONField(
                            blank=True, default=dict,
                            verbose_name='转换后的Pipeline JSON',
                            help_text='录制转换后的 Pipeline JSON',
                        )),
                        ('duration', models.FloatField(
                            default=0, verbose_name='录制时长(秒)',
                            help_text='录制的总时长(秒)',
                        )),
                        ('screenshot_count', models.IntegerField(
                            default=0, verbose_name='截图数量',
                            help_text='录制过程中截图的总数',
                        )),
                        ('resolution', models.CharField(
                            default='1920x1080', max_length=50,
                            verbose_name='分辨率',
                            help_text='录制的屏幕分辨率',
                        )),
                        ('created_at', models.DateTimeField(
                            auto_now_add=True, verbose_name='创建时间',
                            help_text='记录创建的时间戳',
                        )),
                        ('user', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='recordings',
                            to=settings.AUTH_USER_MODEL,
                            verbose_name='用户',
                            help_text='录制所属的用户',
                        )),
                    ],
                    options={
                        'verbose_name': '录制',
                        'verbose_name_plural': '录制',
                        'db_table': 'recording',
                        'ordering': ['-created_at'],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
