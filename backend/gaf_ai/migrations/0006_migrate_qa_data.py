"""Copy data from old qa_* tables to new gaf_ai_qa_* tables (2026-08-04)."""

from django.db import migrations


def copy_qa_data(apps, schema_editor):
    """Copy data from qa_qa_session, qa_qa_message, qa_llmusagelog to new tables."""
    with schema_editor.connection.cursor() as cursor:
        # Check if old tables exist
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='qa_qa_session'")
        if cursor.fetchone()[0] == 0:
            return

        # Copy QASession
        cursor.execute("""
            INSERT OR IGNORE INTO gaf_ai_qa_session (id, question, title, context_snapshot, answer, is_knowledge_entry, user_id, model_name, created_at, updated_at)
            SELECT id, question, title, context_snapshot, answer, is_knowledge_entry, user_id, model_name, created_at, updated_at FROM qa_qa_session
        """)

        # Copy QAMessage
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='qa_qa_message'")
        if cursor.fetchone()[0] > 0:
            cursor.execute("""
                INSERT OR IGNORE INTO gaf_ai_qa_message (id, session_id, role, content, created_at)
                SELECT id, session_id, role, content, created_at FROM qa_qa_message
            """)

        # Copy LLMUsageLog
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='qa_llmusagelog'")
        if cursor.fetchone()[0] > 0:
            cursor.execute("""
                INSERT OR IGNORE INTO gaf_ai_llmusagelog (id, user_id, model_name, input_tokens, output_tokens, cost_estimate, call_type, route, created_at)
                SELECT id, user_id, model_name, input_tokens, output_tokens, cost_estimate, call_type, route, created_at FROM qa_llmusagelog
            """)


class Migration(migrations.Migration):
    """Copy data from old qa tables to new gaf_ai tables."""

    dependencies = [
        ('gaf_ai', '0005_qa_models'),
    ]

    operations = [
        migrations.RunPython(copy_qa_data),
    ]