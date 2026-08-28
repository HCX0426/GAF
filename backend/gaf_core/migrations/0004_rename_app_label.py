"""Rename app_label from 'core' to 'gaf_core' (TD-116).

This is a data-only migration that updates the ``django_migrations`` table
to reflect the new app_label. The ``LogEntry`` model's ``db_table`` is
already explicitly set to ``core_log_entry`` in ``Meta``, so no schema
change is needed — only the app_label changes.

Forward:  UPDATE django_migrations SET app = 'gaf_core' WHERE app = 'core'
Reverse:  UPDATE django_migrations SET app = 'core'      WHERE app = 'gaf_core'
"""

from django.db import migrations


def forwards(apps, schema_editor):
    """Rename app_label 'core' -> 'gaf_core' in django_migrations table."""
    schema_editor.execute(
        "UPDATE django_migrations SET app = 'gaf_core' WHERE app = 'core'"
    )


def backwards(apps, schema_editor):
    """Reverse: rename app_label 'gaf_core' -> 'core'."""
    schema_editor.execute(
        "UPDATE django_migrations SET app = 'core' WHERE app = 'gaf_core'"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('gaf_core', '0003_logentry_dedup_fields'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
