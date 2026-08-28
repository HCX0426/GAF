"""Delete ScreenState and ScreenStateTransition tables.

These tables were created by 0004_screen_state.py, which has been removed
because the ScreenState feature was deleted (only models+editor existed,
agent never consumed them). This migration drops the physical tables on
databases that still have them (e.g. dev DBs where 0004 was previously
applied) while being a safe no-op on fresh DBs (DROP TABLE IF EXISTS).

We cannot use migrations.DeleteModel here because the migration state
never contained ScreenState (0004 was deleted, not just emptied), so
DeleteModel would raise KeyError when trying to remove a non-existent
model from the state.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('gamestate', '0005_game_profile_defaults'),
    ]

    operations = [
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS gamestate_screenstatetransition;',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS gamestate_screenstate;',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
