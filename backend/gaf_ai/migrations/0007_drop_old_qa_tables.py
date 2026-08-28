"""Drop old qa_* tables after data migration (2026-08-04)."""

from django.db import migrations


class Migration(migrations.Migration):
    """Drop old qa_qa_session, qa_qa_message, qa_llmusagelog tables."""

    dependencies = [
        ('gaf_ai', '0006_migrate_qa_data'),
    ]

    operations = [
        migrations.RunSQL(
            "DROP TABLE IF EXISTS qa_qa_session",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS qa_qa_message",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS qa_llmusagelog",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]