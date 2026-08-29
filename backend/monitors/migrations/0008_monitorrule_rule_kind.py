"""TD-420: Add MonitorRule.rule_kind (monitor / game_ui) + backfill historical rows.

Historical data: rows imported from ``resources/*/monitors/*.yaml`` (popup_handler /
story_skip) are game-UI rules that mis-used the MonitorRule table; seed_data rows
(heartbeat / step_duration / consecutive_failures) are genuine monitor rules.
Backfill heuristic: a rule_definition containing ``rules`` (template→action list)
or a name matching popup/story markers is classified as ``game_ui``.
"""

import django.db.models.deletion
import django.db.models.manager
from django.db import migrations, models

import monitors.models


def _classify(row):
    """Return rule_kind for a historical MonitorRule row (id, rule_definition)."""
    rule_id, definition = row
    if not isinstance(definition, dict):
        return 'game_ui'
    # 游戏 UI 规则: rule_definition 含 rules(模板→动作) 列表
    if isinstance(definition.get('rules'), list):
        return 'game_ui'
    # 显式监控语义 type (seed_data: heartbeat/step_duration/consecutive_failures)
    rule_type = str(definition.get('type', ''))
    if rule_type in ('heartbeat', 'step_duration', 'consecutive_failures'):
        return 'monitor'
    # 兜底: 含 template/action 键 → 游戏 UI
    if 'template' in definition or 'action' in definition:
        return 'game_ui'
    return 'monitor'


def backfill_rule_kind(apps, schema_editor):
    """Backfill rule_kind for existing MonitorRule rows."""
    MonitorRule = apps.get_model('monitors', 'MonitorRule')
    rules = list(
        MonitorRule.objects.values_list('id', 'rule_definition'),
    )
    for rule_id, definition in rules:
        kind = _classify((rule_id, definition))
        MonitorRule.objects.filter(pk=rule_id).update(rule_kind=kind)


class Migration(migrations.Migration):
    """Add rule_kind to MonitorRule and backfill existing rows."""

    dependencies = [
        ('monitors', '0007_drop_old_metrics_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='monitorrule',
            name='rule_kind',
            field=models.CharField(
                choices=[('monitor', '监控告警规则'), ('game_ui', '游戏 UI 处理规则')],
                db_index=True,
                default='monitor',
                help_text='monitor=监控告警规则; game_ui=游戏 UI 处理规则(弹窗/剧情)',
                max_length=16,
                verbose_name='规则类型',
            ),
        ),
        migrations.RunPython(
            backfill_rule_kind,
            migrations.RunPython.noop,
        ),
    ]