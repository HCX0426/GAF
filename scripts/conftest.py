"""conftest.py for scripts/ - 让 scripts.source_parser 这样的 import 能跑通

让 pytest 跑 scripts/tests/ 时, 自动把 scripts/ 父目录加到 sys.path
同时把 scripts/{bootstrap,hooks,lessons} 子目录也加到 sys.path,
让 bare import (如 `import check_session_active`) 在脚本移到子目录后继续工作。
"""
import sys
from pathlib import Path

import pytest

# 把 GAF/ 仓库根加到 sys.path (含 scripts/ 包, 可用 `from scripts.xxx import yyy`)
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 把 scripts/ 及其 3 个子目录加到 sys.path, 让 bare import 工作。
# 历史上 scripts/*.py 都在 scripts/ root, 测试用 `import sync_ai_memory` 等
# bare import。Phase 4 重组后这些脚本移到了 bootstrap/hooks/lessons/ 子目录,
# bare import 失效。这里把子目录也加到 sys.path, 让测试无需逐个改 import。
_SCRIPTS_DIR = Path(__file__).resolve().parent
for _subdir in ("", "bootstrap", "hooks", "lessons"):
    _p = _SCRIPTS_DIR / _subdir if _subdir else _SCRIPTS_DIR
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture
def repo_root() -> Path:
    """Real GAF repo root (for integration tests that need the actual repo)."""
    return _REPO_ROOT
