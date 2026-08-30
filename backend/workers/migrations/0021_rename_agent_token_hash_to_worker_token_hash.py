"""Rename Worker token fields + normalize Agent-named options (naming-g G-7 / G-1).

Historical migration 0007_agent_token_hash still introduces the token fields
under their original names (history is immutable); this migration converges
both fresh and already-applied databases onto the final names, and records the
verbose_name/help_text normalization of the Worker model so makemigrations
state matches the model.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workers", "0020_worker_delete_agent_alter_devicegroup_devices_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="worker",
            old_name="agent_token_hash",
            new_name="worker_token_hash",
        ),
        migrations.RenameField(
            model_name="worker",
            old_name="agent_token_preview",
            new_name="worker_token_preview",
        ),
        migrations.AlterModelOptions(
            name="worker",
            options={
                "ordering": ["-id"],
                "verbose_name": "Worker",
                "verbose_name_plural": "Worker",
            },
        ),
        migrations.AlterField(
            model_name="worker",
            name="capabilities",
            field=models.JSONField(
                default=dict,
                verbose_name="能力标签",
                help_text="Worker 支持的能力标签字典",
            ),
        ),
        migrations.AlterField(
            model_name="worker",
            name="cpu_usage",
            field=models.FloatField(
                null=True,
                blank=True,
                verbose_name="CPU 使用率 (%)",
                help_text="Worker 进程 CPU 占用百分比",
            ),
        ),
        migrations.AlterField(
            model_name="worker",
            name="hostname",
            field=models.CharField(
                max_length=255,
                verbose_name="主机名",
                help_text="Worker 所在主机的名称",
            ),
        ),
        migrations.AlterField(
            model_name="worker",
            name="ip_address",
            field=models.GenericIPAddressField(
                null=True,
                blank=True,
                verbose_name="IP 地址",
                help_text="Worker 所在主机的 IP 地址",
            ),
        ),
        migrations.AlterField(
            model_name="worker",
            name="is_local",
            field=models.BooleanField(
                default=False,
                verbose_name="是否本地 Worker",
                help_text="标记是否为本地 Worker",
            ),
        ),
        migrations.AlterField(
            model_name="worker",
            name="memory_usage",
            field=models.FloatField(
                null=True,
                blank=True,
                verbose_name="内存使用率 (%)",
                help_text="Worker 进程内存占用百分比",
            ),
        ),
        migrations.AlterField(
            model_name="worker",
            name="os_info",
            field=models.CharField(
                max_length=255,
                blank=True,
                verbose_name="操作系统信息",
                help_text="Worker 主机的操作系统描述",
            ),
        ),
        migrations.AlterField(
            model_name="worker",
            name="screenshot_fps",
            field=models.FloatField(
                null=True,
                blank=True,
                verbose_name="截图帧率 (FPS)",
                help_text="Worker 支持的截图帧率",
            ),
        ),
    ]