# Generated manually for PluginPackage and PluginSandbox models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('plugins', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PluginPackage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True, verbose_name='插件名称')),
                ('version', models.CharField(max_length=50, verbose_name='版本号')),
                ('author', models.CharField(blank=True, default='', max_length=150, verbose_name='作者')),
                ('description', models.TextField(blank=True, default='', verbose_name='描述')),
                ('manifest', models.JSONField(default=dict, verbose_name='manifest 信息')),
                ('package_path', models.CharField(blank=True, default='', max_length=500, verbose_name='包文件路径')),
                ('is_installed', models.BooleanField(default=False, verbose_name='是否已安装')),
                ('is_active', models.BooleanField(default=False, verbose_name='是否启用')),
                ('installed_at', models.DateTimeField(blank=True, null=True, verbose_name='安装时间')),
                ('checksum', models.CharField(blank=True, default='', max_length=64, verbose_name='校验和')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '插件包',
                'verbose_name_plural': '插件包',
                'db_table': 'plugins_pluginpackage',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PluginSandbox',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pid', models.IntegerField(blank=True, null=True, verbose_name='进程ID')),
                ('status', models.CharField(choices=[('idle', '空闲'), ('running', '运行中'), ('stopped', '已停止'), ('error', '错误')], default='idle', max_length=50, verbose_name='状态')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('plugin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sandboxes', to='plugins.pluginpackage', verbose_name='插件')),
            ],
            options={
                'verbose_name': '插件沙箱',
                'verbose_name_plural': '插件沙箱',
                'db_table': 'plugins_pluginsandbox',
                'ordering': ['-created_at'],
            },
        ),
    ]