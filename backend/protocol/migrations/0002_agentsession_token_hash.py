"""C5 fix: introduce AgentSession.token_hash + token_preview and backfill from capabilities.

Previously AgentSession stored its connection token as plaintext in
capabilities['agent_token']. This migration:
1. Adds token_hash (SHA-256 hex) and token_preview (first4...last4) fields.
2. For every AgentSession whose capabilities contain 'agent_token', computes
   hash + preview and stores them in the new fields, then removes the
   plaintext entry from capabilities.
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


def backfill_session_tokens_forwards(apps, schema_editor):
    AgentSession = apps.get_model('protocol', 'AgentSession')
    for session in AgentSession.objects.all():
        caps = session.capabilities or {}
        if not isinstance(caps, dict):
            continue
        plaintext = caps.pop('agent_token', None)
        if not plaintext:
            continue
        session.token_hash = _hash_token(plaintext)
        session.token_preview = _make_preview(plaintext)
        session.capabilities = caps
        session.save(update_fields=['capabilities', 'token_hash', 'token_preview'])


def unbackfill_session_tokens_backwards(apps, schema_editor):
    """Best-effort reverse: cannot restore plaintext from hash."""
    AgentSession = apps.get_model('protocol', 'AgentSession')
    for session in AgentSession.objects.all():
        caps = session.capabilities or {}
        if not isinstance(caps, dict):
            caps = {}
        # Hash cannot be reversed; just clear hash + preview.
        session.token_hash = None
        session.token_preview = ''
        session.capabilities = caps
        session.save(update_fields=['capabilities', 'token_hash', 'token_preview'])


class Migration(migrations.Migration):

    dependencies = [
        ('protocol', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentsession',
            name='token_hash',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='C5: SHA-256(token) 十六进制摘要，取代 capabilities.agent_token 明文存储。',
                max_length=64,
                null=True,
                verbose_name='连接 Token 哈希 (SHA-256)',
            ),
        ),
        migrations.AddField(
            model_name='agentsession',
            name='token_preview',
            field=models.CharField(
                blank=True,
                default='',
                help_text='C5: 前后各 4 位字符预览，用于列表展示，不暴露完整 Token。',
                max_length=20,
                verbose_name='Token 预览',
            ),
        ),
        migrations.RunPython(
            backfill_session_tokens_forwards,
            reverse_code=unbackfill_session_tokens_backwards,
        ),
    ]
