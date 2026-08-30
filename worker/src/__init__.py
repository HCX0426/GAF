"""GAF Worker 客户端 — 设备控制层."""

import sys
from pathlib import Path

# The daemon starts this package via ``python -m src`` with cwd=worker/
# (scripts/gaf_daemon.py), which puts worker/ (not worker/src/) on sys.path.
# The flat imports in this package (client/, core/, devices/, image/,
# monitor/, utils/) resolve only when worker/src is on sys.path, so bootstrap
# it here — this module is always imported first when ``-m src`` runs.
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

__version__ = "0.1.0"
