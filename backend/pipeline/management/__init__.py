"""Django management command for routine.json → TaskChain import (TD-110 Phase 3).

Usage:
    python manage.py import_routine <routine_path> --game-profile <id> [--user <username>]

Example:
    python manage.py import_routine resources/BrownDust-II/routine.json \\
        --game-profile 1 --user admin
"""
