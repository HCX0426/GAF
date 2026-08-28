"""R37-P3 Stage 7 Task 20b: remove AppSettings from tasks app state.

Companion to settings/migrations/0005_appsettings.py. Together they move the
AppSettings model from the `tasks` app to the `settings` app without touching
the physical `tasks_appsettings` table.

This migration is STATE-ONLY (SeparateDatabaseAndState with empty
database_operations): the physical table stays in the DB and is now owned
by settings.AppSettings (same db_table). Running this DeleteModel only updates
Django's migration state; it does NOT drop the table.

Dependency ordering: this migration depends on settings/0005_appsettings so the
receiving app's CreateModel runs first. Briefly AppSettings exists in both apps'
state (harmless — Django does not enforce db_table uniqueness across apps at
migration time), then this migration removes it from tasks. Net effect: the
model is "moved" from tasks to settings.

Callers updated to import from settings.models:
- accounts/views.py (3 sites: register toggle, InitStatusView, SetupView)
- settings/admin.py (AppSettingsAdmin registration)
- settings/views.py (AppSettingsViewSet)
- settings/serializers.py (AppSettingsSerializer)
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0035_remove_auditlog'),
        ('settings', '0005_appsettings'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name='AppSettings',
                ),
            ],
            database_operations=[],
        ),
    ]
