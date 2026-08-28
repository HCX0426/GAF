import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ModelEvaluation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('system_prompt', models.TextField(blank=True, default='')),
                ('test_cases', models.JSONField(default=list, help_text='List of test input strings')),
                ('models_config', models.JSONField(default=list, help_text='List of model configs to evaluate')),
                ('scoring_criteria', models.JSONField(default=list, help_text='List of scoring criteria: [{name, weight, description}]')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('error_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='model_evaluations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'ai_model_evaluation',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ModelEvaluationResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('test_case_index', models.IntegerField(default=0, help_text='Index into evaluation.test_cases')),
                ('provider', models.CharField(max_length=50)),
                ('model_name', models.CharField(max_length=100)),
                ('output_text', models.TextField(blank=True, default='')),
                ('input_tokens', models.IntegerField(default=0)),
                ('output_tokens', models.IntegerField(default=0)),
                ('cost', models.DecimalField(decimal_places=6, default=0, max_digits=10)),
                ('latency_ms', models.IntegerField(default=0, help_text='Response latency in milliseconds')),
                ('scores', models.JSONField(default=dict)),
                ('average_score', models.FloatField(default=0, help_text='Weighted average score (0-10)')),
                ('error', models.TextField(blank=True, default='')),
                ('is_success', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('evaluation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='results', to='gaf_ai.modelevaluation')),
            ],
            options={
                'db_table': 'ai_model_evaluation_result',
                'ordering': ['test_case_index', 'model_name'],
            },
        ),
        migrations.AddIndex(
            model_name='modelevaluation',
            index=models.Index(fields=['status'], name='idx_modelev_status'),
        ),
        migrations.AddIndex(
            model_name='modelevaluation',
            index=models.Index(fields=['created_by', '-created_at'], name='idx_modelev_user_created'),
        ),
        migrations.AddIndex(
            model_name='modelevaluationresult',
            index=models.Index(fields=['evaluation', 'test_case_index'], name='idx_modelevr_eval_case'),
        ),
        migrations.AddIndex(
            model_name='modelevaluationresult',
            index=models.Index(fields=['evaluation', 'model_name'], name='idx_modelevr_eval_model'),
        ),
        migrations.AlterUniqueTogether(
            name='modelevaluationresult',
            unique_together={('evaluation', 'test_case_index', 'model_name')},
        ),
    ]
