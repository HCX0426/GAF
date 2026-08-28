"""skill_sync — domain package for sync_skills.py (s39 split, TD-365 6/9).

Modules:
  constants   — shared constants/regexes (zero deps)
  io_utils    — file/text helpers (depends on constants)
  checks      — 5 consistency check functions (depends on constants)
  changelog   — --changelog command + report helpers (depends on constants + io_utils)
  timestamps  — --update-timestamps command (depends on constants + io_utils)

All submodules have ZERO main-file dependency (N202 18: no import cycles);
sync_skills.py re-exports every public/private name for backward compat.
"""
