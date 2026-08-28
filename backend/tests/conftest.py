"""pytest 配置"""
import os
import shutil
from pathlib import Path

import django
import pytest

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
django.setup()

# Default resource packs that must never be cleaned up by the autouse fixture.
# Spec-52: Test side-effect cleanup for ResourcePack create API (TD-004 Option A:
# resources/ is the single source of truth, so API create copies pack to
# resources/<name>/, which leaks as untracked files without this fixture).
_DEFAULT_RESOURCE_PACKS = {"BrownDust-II", "default"}
_RESOURCES_ROOT = Path(__file__).resolve().parent.parent.parent / "resources"


@pytest.fixture(autouse=True)
def cleanup_test_resource_packs():
    """Auto-cleanup resource pack dirs created by tests under resources/.

    Tests in test_resource_pack.py and test_integration.py call the
    ResourcePack create API, which copies the pack to resources/<name>/
    (TD-004 Option A: resources/ is the single source of truth). Without
    cleanup, these test artifacts accumulate as untracked files in git status.

    Strategy: snapshot resources/ subdirs before test, remove new ones
    after (preserving default packs: BrownDust-II, default).
    """
    before = set()
    if _RESOURCES_ROOT.exists():
        before = {p.name for p in _RESOURCES_ROOT.iterdir() if p.is_dir()}

    yield

    if _RESOURCES_ROOT.exists():
        after = {p.name for p in _RESOURCES_ROOT.iterdir() if p.is_dir()}
        new_dirs = after - before - _DEFAULT_RESOURCE_PACKS
        for name in new_dirs:
            shutil.rmtree(str(_RESOURCES_ROOT / name), ignore_errors=True)
