"""Resource path resolver for Pipeline template/asset loading.

Resolves relative template paths (e.g. "BrownDust-II/templates/guild_btn.png")
against the GAF resources root, with fallback to absolute paths and
extension auto-discovery.

Resolution order:
1. Absolute path → use as-is if it exists
2. GAF_RESOURCE_ROOT env var / <path>
3. <CWD>/resources/<path>
4. <CWD>/../resources/<path>  (agent runs from GAF/agent/, resources in GAF/resources/)
5. Walk up from this file to find a "resources" sibling directory
6. <root>/<path> (direct match under each root)
7. <root>/<game>/templates/<path> for each <game> subdir of <root>/ —
   supports BD2 short paths like "public/主界面" by searching
   "BrownDust-II/templates/public/主界面" and "default/templates/public/主界面"
8. If no extension, retry candidates with .png/.jpg/.jpeg/.bmp/.webp
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Common image extensions to try when a path has no extension
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def _candidate_roots() -> list[Path]:
    """Build the list of candidate resource roots, in priority order."""
    roots: list[Path] = []

    # 1. Explicit env var
    env_root = os.environ.get("GAF_RESOURCE_ROOT", "")
    if env_root:
        roots.append(Path(env_root))

    # 2. CWD-based roots
    cwd = Path.cwd()
    roots.append(cwd / "resources")
    roots.append(cwd.parent / "resources")

    # 3. Walk up from this file (agent/src/engine/resource_resolver.py)
    #    to find the GAF root (which contains a "resources" sibling).
    #    __file__ = agent/src/engine/resource_resolver.py
    #    parent chain: engine/ -> src/ -> agent/ -> GAF/
    here = Path(__file__).resolve().parent  # agent/src/engine/
    for ancestor in [here.parent.parent, here.parent.parent.parent]:
        candidate = ancestor / "resources"
        if candidate not in roots:
            roots.append(candidate)

    return roots


def _template_subdirs(root: Path) -> list[Path]:
    """Return <root>/<game>/templates/ directories that exist.

    GAF resource packs follow the structure:
        <root>/BrownDust-II/templates/public/主界面.png
        <root>/default/templates/public/返回键1.png

    BD2 pipeline authors use short paths like "public/主界面" (without the
    "BrownDust-II/templates/" prefix). This helper enumerates all
    <root>/<game>/templates/ directories so resolve_resource_path can try
    each one.
    """
    subdirs: list[Path] = []
    if not root.is_dir():
        return subdirs
    try:
        for game_dir in root.iterdir():
            if not game_dir.is_dir():
                continue
            templates_dir = game_dir / "templates"
            if templates_dir.is_dir():
                subdirs.append(templates_dir)
    except (PermissionError, OSError) as exc:
        logger.debug("Cannot enumerate %s: %s", root, exc)
    return subdirs


def resolve_resource_path(path_str: str) -> Path | None:
    """Resolve a relative resource path to an existing file.

    Args:
        path_str: Absolute path, or relative path under resources/
                  (e.g. "BrownDust-II/templates/guild_btn.png" or the
                  BD2 short form "public/主界面"). Extension is optional;
                  .png/.jpg/.jpeg/.bmp/.webp are tried when the bare path
                  does not exist.

    Returns:
        Path to the existing file, or None if not found.
    """
    if not path_str:
        return None

    p = Path(path_str)

    # Absolute path: use as-is
    if p.is_absolute():
        if p.exists():
            return p
        # Try with extension if no suffix
        if not p.suffix:
            for ext in _IMAGE_EXTENSIONS:
                with_ext = p.with_suffix(ext)
                if with_ext.exists():
                    return with_ext
        return None

    roots = _candidate_roots()

    # Pass 1: direct match under each root (handles full paths like
    # "BrownDust-II/templates/guild_btn.png")
    for root in roots:
        candidate = root / path_str
        if candidate.exists():
            return candidate

    # Pass 2: <root>/<game>/templates/<path> — handles BD2 short paths
    # like "public/主界面" by searching all game packs under each root.
    # This makes GAF compatible with BD2-AUTO pipeline conventions where
    # template paths omit the game/templates prefix.
    for root in roots:
        for templates_dir in _template_subdirs(root):
            candidate = templates_dir / path_str
            if candidate.exists():
                return candidate

    # Pass 3: retry with common image extensions when path has no suffix
    if not p.suffix:
        for root in roots:
            for ext in _IMAGE_EXTENSIONS:
                candidate = (root / path_str).with_suffix(ext)
                if candidate.exists():
                    return candidate
        # Extension retry over <game>/templates/ subdirs too
        for root in roots:
            for templates_dir in _template_subdirs(root):
                for ext in _IMAGE_EXTENSIONS:
                    candidate = (templates_dir / path_str).with_suffix(ext)
                    if candidate.exists():
                        return candidate

    logger.debug(
        "Resource not found: %s (searched roots: %s)",
        path_str,
        [str(r) for r in roots],
    )
    return None
