"""Rename app_label from 'ai' to 'gaf_ai' (TD-116 Phase 2).

Data-only migration: updates django_migrations table to reflect the new
app_label. All model db_table names keep their ``ai_*`` prefix (explicit
in Meta), so no schema change is needed.

Forward:  UPDATE django_migrations SET app = 'gaf_ai' WHERE app = 'ai'
Reverse:  UPDATE django_migrations SET app = 'ai'       WHERE app = 'gaf_ai'
"""

from django.db import migrations


def forwards(apps, schema_editor):
    """Rename app_label 'ai' -> 'gaf_ai' in django_migrations table."""
    schema_editor.execute(
        "UPDATE django_migrations SET app = 'gaf_ai' WHERE app = 'ai'"
    )


def backwards(apps, schema_editor):
    """Reverse: rename app_label 'gaf_ai' -> 'ai'."""
    schema_editor.execute(
        "UPDATE django_migrations SET app = 'ai' WHERE app = 'gaf_ai'"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('gaf_ai', '0003_agent_session'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
