from django.db import migrations, models


class Migration(migrations.Migration):
    """TD-259 #18: Add composite indexes for TaskExecution hot query paths.

    Indexes added (P2):
      - (chain_execution, status): chain-mode execution status lookups
      - (device, status): per-device execution status filtering
      - (game_account, status): per-account execution status filtering

    Note: chain_execution is a nullable FK; Django/Postgres handle NULL in
    composite indexes without issue.
    """

    dependencies = [("tasks", "0047_taskexecution_agent_blank")]

    operations = [
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["chain_execution", "status"],
                name="idx_taskexec_chain_status",
            ),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["device", "status"],
                name="idx_taskexec_device_status",
            ),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["game_account", "status"],
                name="idx_taskexec_account_status",
            ),
        ),
    ]
