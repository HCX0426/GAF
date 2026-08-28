"""Add GameProfile.device_type_hint field.

GameProfile 之前没有字段明确声明游戏运行在哪种设备类型上，只有
screenshot_methods 间接暗示 (wgc/gdi/bitblt → windows, adb/minicap →
emulator)。这导致设备绑定时 AI 可能误选模拟器去跑 Windows 窗口游戏
(BrownDust II 事件)。

本迁移加 device_type_hint 字段，并通过 screenshot_methods 推断回填
现有 GameProfile：
- 含 wgc / gdi / bitblt / printwindow → 'windows'
- 含 adb / minicap / scrcpy          → 'emulator'
- 其他                                → '' (留空，由 Agent 上报决定)
"""
from django.db import migrations, models


_WINDOWS_METHODS = {'wgc', 'gdi', 'bitblt', 'printwindow'}
_EMULATOR_METHODS = {'adb', 'minicap', 'scrcpy', 'adb_screencap'}


def infer_device_type_hint(screenshot_methods):
    """Infer device_type_hint from screenshot_methods list.

    Returns 'windows' / 'emulator' / '' (empty when indeterminate).
    """
    methods = {str(m).lower() for m in (screenshot_methods or [])}
    if methods & _WINDOWS_METHODS:
        return 'windows'
    if methods & _EMULATOR_METHODS:
        return 'emulator'
    return ''


def populate_device_type_hint(apps, schema_editor):
    """Back-fill device_type_hint for existing GameProfile rows."""
    GameProfile = apps.get_model('gamestate', 'GameProfile')
    for profile in GameProfile.objects.all():
        hint = infer_device_type_hint(profile.screenshot_methods)
        if hint:
            profile.device_type_hint = hint
            profile.save(update_fields=['device_type_hint'])


def reverse_populate(apps, schema_editor):
    """Reverse is a no-op — field is being removed by RemoveField."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('gamestate', '0007_gameprofile_routine_path'),
    ]

    operations = [
        migrations.AddField(
            model_name='gameprofile',
            name='device_type_hint',
            field=models.CharField(
                blank=True,
                choices=[('windows', 'Windows 窗口游戏'), ('emulator', '模拟器游戏')],
                default='',
                help_text='明确该游戏运行的设备类型，避免设备绑定误选。'
                          'windows = 原生 Windows 窗口游戏 (通过 window_title/hwnd 匹配)；'
                          'emulator = 安卓模拟器游戏 (通过 adb_serial 匹配)。'
                          '留空表示未指定，由 Agent 上报的 device_type 决定。',
                max_length=20,
                verbose_name='设备类型提示',
            ),
        ),
        migrations.RunPython(populate_device_type_hint, reverse_populate),
    ]
