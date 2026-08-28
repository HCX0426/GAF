"""C4 fix: introduce agent_token_hash + agent_token_preview and backfill from plaintext.

This migration:
1. Adds agent_token_hash (SHA-256 hex) and agent_token_preview (first4...last4).
2. For every Agent with a non-empty agent_token, computes hash + preview and
   stores them in the new fields, then nulls out agent_token to remove
   plaintext from the database.
"""

import hashlib

from django.db import migrations, models


def _hash_token(token):
    if not token:
        return ''
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _make_preview(token):
    if not token:
        return ''
    if len(token) > 8:
        return f"{token[:4]}...{token[-4:]}"
    return token[:4] + '...'


def backfill_agent_tokens_forwards(apps, schema_editor):
    Agent = apps.get_model('agents', 'Agent')
    for agent in Agent.objects.exclude(agent_token__isnull=True).exclude(agent_token__exact=''):
        plaintext = agent.agent_token
        agent.agent_token_hash = _hash_token(plaintext)
        agent.agent_token_preview = _make_preview(plaintext)
        # Null out plaintext after deriving hash + preview.
        agent.agent_token = None
        agent.save(update_fields=['agent_token', 'agent_token_hash', 'agent_token_preview'])


def unbackfill_agent_tokens_backwards(apps, schema_editor):
    """Best-effort reverse: cannot restore plaintext from hash.

    Leaves agent_token_hash + agent_token_preview as-is. The forward migration
    is destructive with respect to plaintext tokens; rollback should be
    accompanied by re-issuing tokens via the API.
    """
    Agent = apps.get_model('agents', 'Agent')
    Agent.objects.update(agent_token=None)


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0006_device_metadata_enhancement'),
    ]

    operations = [
        migrations.AddField(
            model_name='agent',
            name='agent_token_hash',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='C4: SHA-256(token) 十六进制摘要，用于数据库查找。',
                max_length=64,
                null=True,
                verbose_name='鉴权 Token 哈希 (SHA-256)',
            ),
        ),
        migrations.AddField(
            model_name='agent',
            name='agent_token_preview',
            field=models.CharField(
                blank=True,
                default='',
                help_text='C4: 前后各 4 位字符预览，用于列表展示，不暴露完整 Token。',
                max_length=20,
                verbose_name='Token 预览',
            ),
        ),
        migrations.AlterField(
            model_name='agent',
            name='agent_token',
            field=models.CharField(
                blank=True,
                help_text='C4: 已废弃，仅保留用于数据迁移。新代码请使用 agent_token_hash。',
                max_length=255,
                null=True,
                unique=True,
                verbose_name='鉴权 Token (已废弃)',
            ),
        ),
        migrations.RunPython(
            backfill_agent_tokens_forwards,
            reverse_code=unbackfill_agent_tokens_backwards,
        ),
    ]
