"""N1139: Set default screenshot_method / input_method to 'auto'.

Previously both fields defaulted to '' (empty string), which meant:
- Device.screenshot_method was empty until a user manually configured it
- Device.input_method was empty forever (no auto-selection logic existed)
- Agent-side config defaults to 'auto' but backend defaults to '', causing
  inconsistency between agent and backend when interpreting unset values.

This migration:
1. Changes field defaults from '' to 'auto'.
2. Backfills existing rows: empty string -> 'auto' so legacy devices pick up
   the new default behavior (platform handler picks best method at runtime).

Note: devices with explicit user-set methods (e.g. 'wgc', 'sendinput') are
NOT touched — only empty-string values are backfilled.
"""

from django.db import migrations, models


def backfill_empty_to_auto(apps, schema_editor):
    """Set screenshot_method / input_method to 'auto' where they are empty."""
    Device = apps.get_model('agents', 'Device')
    Device.objects.filter(screenshot_method='').update(screenshot_method='auto')
    Device.objects.filter(input_method='').update(input_method='auto')


def revert_auto_to_empty(apps, schema_editor):
    """Revert: set 'auto' back to '' (only for values that are exactly 'auto')."""
    Device = apps.get_model('agents', 'Device')
    Device.objects.filter(screenshot_method='auto').update(screenshot_method='')
    Device.objects.filter(input_method='auto').update(input_method='')


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0007_agent_token_hash'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='screenshot_method',
            field=models.CharField(
                blank=True,
                default='auto',
                help_text='设备使用的截图方式标识，"auto" 表示由平台 handler 自动选择',
                max_length=64,
                verbose_name='截图方式',
            ),
        ),
        migrations.AlterField(
            model_name='device',
            name='input_method',
            field=models.CharField(
                blank=True,
                default='auto',
                help_text='设备使用的输入方式标识，"auto" 表示由平台 handler 自动选择',
                max_length=64,
                verbose_name='输入方式',
            ),
        ),
        migrations.RunPython(backfill_empty_to_auto, revert_auto_to_empty),
    ]
