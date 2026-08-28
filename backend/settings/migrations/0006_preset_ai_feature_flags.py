"""S5 Task A1 / P2-5: preset two AI-related FeatureFlag rows.

Seeds ``ai_assistant_enabled`` and ``langgraph_agent_enabled`` so that
operators can toggle the QA endpoint and the LangGraph agent from the
FeatureFlag admin / API without writing SQL.

Idempotent: each row is created via ``get_or_create`` so re-running the
migration (or running it on a DB where the rows already exist) is a no-op.
The reverse migration deliberately does NOT delete the rows — operators
may have tuned ``enabled`` / ``rollout_percentage`` and we must not wipe
their configuration.
"""

from django.db import migrations


def preset_ai_feature_flags(apps, schema_editor):
    """Create the two AI FeatureFlag rows if they do not yet exist."""
    FeatureFlag = apps.get_model('settings', 'FeatureFlag')

    FeatureFlag.objects.get_or_create(
        name='ai_assistant_enabled',
        defaults={
            'description': 'Enable AI assistant QA endpoint',
            'enabled': True,
        },
    )
    FeatureFlag.objects.get_or_create(
        name='langgraph_agent_enabled',
        defaults={
            'description': 'Enable LangGraph agent deep analysis',
            'enabled': True,
        },
    )


def reverse_preset_ai_feature_flags(apps, schema_editor):
    """No-op reverse: do not delete operator-tuned flags.

    If a deployment truly wants the rows gone, they can be removed via
    the FeatureFlag admin UI. Removing them in a migration rollback
    would silently discard any customization.
    """
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0005_appsettings'),
    ]

    operations = [
        migrations.RunPython(
            preset_ai_feature_flags,
            reverse_code=reverse_preset_ai_feature_flags,
        ),
    ]
