"""Create NotificationPreference model for per-user notification settings."""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add NotificationPreference (OneToOne per user) for preferences API."""

    dependencies = [
        ('notifications', '0002_alertrule'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('desktop_notification', models.BooleanField(default=True, verbose_name='桌面通知')),
                ('sound_alert', models.BooleanField(default=True, verbose_name='声音提醒')),
                ('system_notification', models.BooleanField(default=True, verbose_name='系统通知')),
                ('alert_notification', models.BooleanField(default=True, verbose_name='告警通知')),
                ('community_notification', models.BooleanField(default=False, verbose_name='社区通知')),
                ('quiet_hours_start', models.TimeField(blank=True, null=True, verbose_name='静默开始时间')),
                ('quiet_hours_end', models.TimeField(blank=True, null=True, verbose_name='静默结束时间')),
                ('retention_days', models.IntegerField(default=30, help_text='超过 N 天的通知自动清理', verbose_name='通知保留天数')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, related_name='notification_preference', to=settings.AUTH_USER_MODEL, verbose_name='用户')),
            ],
            options={
                'verbose_name': '通知偏好',
                'verbose_name_plural': '通知偏好',
                'db_table': 'notifications_notification_preference',
            },
        ),
    ]
