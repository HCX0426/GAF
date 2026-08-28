# Generated migration for OAuth and 2FA fields on User model
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_apikey_gameaccount_auditlog_loginhistory'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='oauth_provider',
            field=models.CharField(blank=True, choices=[('github', 'GitHub'), ('google', 'Google')], max_length=20, null=True, verbose_name='OAuth 提供商'),
        ),
        migrations.AddField(
            model_name='user',
            name='oauth_uid',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='OAuth 用户ID'),
        ),
        migrations.AddField(
            model_name='user',
            name='totp_secret',
            field=models.CharField(blank=True, max_length=64, null=True, verbose_name='TOTP 密钥'),
        ),
        migrations.AddField(
            model_name='user',
            name='totp_enabled',
            field=models.BooleanField(default=False, verbose_name='2FA 已启用'),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(fields=['oauth_provider', 'oauth_uid'], name='idx_user_oauth'),
        ),
    ]