from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('monitors', '0002_alter_monitorevent_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='monitorevent',
            name='severity',
            field=models.CharField(
                choices=[
                    ('P0', 'P0 紧急'),
                    ('P1', 'P1 高'),
                    ('P2', 'P2 中'),
                    ('P3', 'P3 低'),
                ],
                default='P2',
                help_text='P0=紧急/P1=高/P2=中/P3=低, 用于 P-024 告警升级策略',
                max_length=2,
                verbose_name='严重级别',
            ),
        ),
        migrations.AddField(
            model_name='monitorevent',
            name='acknowledged_at',
            field=models.DateTimeField(
                blank=True,
                help_text='人工确认处理的时间, null=未确认',
                null=True,
                verbose_name='确认时间',
            ),
        ),
        migrations.AddField(
            model_name='monitorevent',
            name='acknowledged_by',
            field=models.ForeignKey(
                blank=True,
                help_text=None,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='acknowledged_alerts',
                to=settings.AUTH_USER_MODEL,
                verbose_name='确认人',
            ),
        ),
        migrations.AddField(
            model_name='monitorevent',
            name='escalated_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Celery 任务自动升级的时间, null=未升级',
                null=True,
                verbose_name='升级时间',
            ),
        ),
        migrations.AddIndex(
            model_name='monitorevent',
            index=models.Index(
                fields=['severity', 'acknowledged_at'],
                name='idx_monitorevent_sev_ack',
            ),
        ),
    ]
