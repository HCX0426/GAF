"""Copy SLAMetric data from metrics_slametric to monitors_slametric."""

from django.db import migrations


def copy_slametric_data(apps, schema_editor):
    """Copy SLAMetric rows from old metrics_slametric table to new monitors_slametric table."""
    with schema_editor.connection.cursor() as cursor:
        # Check if the old table exists and has data
        cursor.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name='metrics_slametric'
        """)
        if cursor.fetchone()[0] == 0:
            return  # Old table doesn't exist, nothing to migrate

        # Copy data from old table to new table
        cursor.execute("""
            INSERT OR IGNORE INTO monitors_slametric (id, agent_id, metric_name, value, labels, timestamp)
            SELECT id, agent_id, metric_name, value, labels, timestamp
            FROM metrics_slametric
        """)


class Migration(migrations.Migration):
    """Data migration: copy SLAMetric data from metrics app to monitors app."""

    dependencies = [
        ('monitors', '0005_slametric'),
    ]

    operations = [
        migrations.RunPython(copy_slametric_data, reverse_code=migrations.RunPython.noop),
    ]