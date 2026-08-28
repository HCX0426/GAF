"""Create QA model tables (migrated from qa app — 2026-08-04)."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Create gaf_ai_qa_session, gaf_ai_qa_message, gaf_ai_llmusagelog tables."""

    dependencies = [
        ('gaf_ai', '0004_rename_app_label'),
    ]

    operations = [
        migrations.CreateModel(
            name='QASession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question', models.TextField(verbose_name='问题')),
                ('title', models.CharField(blank=True, default='', max_length=200, verbose_name='标题')),
                ('context_snapshot', models.JSONField(default=dict, verbose_name='上下文快照')),
                ('answer', models.TextField(blank=True, verbose_name='回答')),
                ('is_knowledge_entry', models.BooleanField(default=False, verbose_name='是否为知识条目')),
                ('model_name', models.CharField(blank=True, max_length=100, verbose_name='模型名称')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='qa_sessions', to=settings.AUTH_USER_MODEL, verbose_name='提问用户')),
            ],
            options={
                'db_table': 'gaf_ai_qa_session',
                'ordering': ['-created_at'],
                'verbose_name': '问答会话',
                'verbose_name_plural': '问答会话',
                'indexes': [models.Index(fields=['is_knowledge_entry'], name='idx_gafai_qasession_knowledge')],
            },
        ),
        migrations.CreateModel(
            name='QAMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant'), ('system', 'System')], max_length=20, verbose_name='角色')),
                ('content', models.TextField(verbose_name='内容')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='gaf_ai.qasession', verbose_name='所属会话')),
            ],
            options={
                'db_table': 'gaf_ai_qa_message',
                'ordering': ['created_at'],
                'verbose_name': '问答消息',
                'verbose_name_plural': '问答消息',
                'indexes': [models.Index(fields=['session', 'created_at'], name='idx_gafai_qamessage_session')],
            },
        ),
        migrations.CreateModel(
            name='LLMUsageLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('model_name', models.CharField(max_length=100, verbose_name='模型名称')),
                ('input_tokens', models.IntegerField(default=0, verbose_name='输入 Token 数')),
                ('output_tokens', models.IntegerField(default=0, verbose_name='输出 Token 数')),
                ('cost_estimate', models.DecimalField(decimal_places=6, default=0, max_digits=10, verbose_name='成本估算')),
                ('call_type', models.CharField(blank=True, max_length=50, verbose_name='调用类型')),
                ('route', models.CharField(blank=True, default='', max_length=20, verbose_name='降级路由')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='llm_usage_logs', to=settings.AUTH_USER_MODEL, verbose_name='用户')),
            ],
            options={
                'db_table': 'gaf_ai_llmusagelog',
                'ordering': ['-created_at'],
                'verbose_name': 'LLM 用量日志',
                'verbose_name_plural': 'LLM 用量日志',
                'indexes': [models.Index(fields=['user', 'created_at'], name='idx_gafai_llmu_user_created')],
            },
        ),
    ]