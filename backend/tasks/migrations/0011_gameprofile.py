# Generated migration for GameProfile model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0010_crashreport_templateeffectiveness_avg_confidence_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='GameProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('game_name', models.CharField(max_length=255, unique=True, verbose_name='游戏名称')),
                ('screenshot_methods', models.JSONField(default=list, verbose_name='推荐截图方式排序列表')),
                ('ocr_language', models.CharField(default='ch', max_length=50, verbose_name='OCR 语言')),
                ('ui_reference_resolution', models.JSONField(default=dict, verbose_name='UI参考分辨率 {w, h}')),
                ('known_popups', models.JSONField(default=list, verbose_name='已知弹窗模板列表')),
                ('resolution_strategy', models.CharField(default='scale', max_length=50, verbose_name='分辨率适配策略')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'db_table': 'game_profile',
                'ordering': ['game_name'],
                'verbose_name': '游戏档案',
                'verbose_name_plural': '游戏档案',
            },
        ),
    ]