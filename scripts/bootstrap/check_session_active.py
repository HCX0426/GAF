"""check_session_active.py — Cross-platform session active binding for GAF.

This script implements a 24-hour TTL session mechanism that prevents stale
AIs from continuing to work after the human operator has left the desk.

Cross-platform binding strategy (N58 fix):
- Linux/macOS: inode + device (st_ino + st_dev) is stable.
- Windows NTFS: st_ino is unreliable across calls; use (size, mtime_ns, ctime_ns)
  as the binding hash. This is a fingerprint of the file's identity at a
  point in time, not a hardware signature.

Usage:
    python check_session_active.py --create   # create a fresh session
    python check_session_active.py --check    # verify the current session
    python check_session_active.py --destroy  # remove the session file
    python check_session_active.py --show     # print binding details
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: F401  (must be first; reconfigures stdout to UTF-8)

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

# Resolve session file path: GAF/.trash/.gaf_session_active
# __file__ = .../GAF/scripts/bootstrap/check_session_active.py
# parents[0] = .../GAF/scripts/bootstrap
# parents[1] = .../GAF/scripts
# parents[2] = .../GAF  ← this is the GAF repo root
# The session file lives in .trash/ (N125 temp dir, gitignored) so the repo
# root stays clean of runtime artifacts.
REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_FILE = REPO_ROOT / ".trash" / ".gaf_session_active"
TTL_SECONDS = 24 * 60 * 60  # 24 hours


def compute_binding_hash() -> str:
    """Compute a 16-char cross-platform binding hash for SESSION_FILE.

    Strategy: use the SHA-256 of the file's *current content with the
    binding_hash field stripped*. This makes the binding robust to:

    - Windows: st_ino is unreliable; st_ctime is "metadata change time" not
      creation time; st_mtime changes on every write. None of these are
      stable for a self-referential fingerprint.
    - Linux/macOS: st_ino is stable, but using inode ties the binding to
      filesystem identity (problematic for git worktrees, copy-on-write,
      overlay filesystems).

    Content-based binding: any tampering that changes the file payload
    (which includes the binding_hash field itself, since we strip it)
    will change the hash, and any tampering that DOESN'T change the
    payload can be detected by comparing the expected binding.
    """
    raw_bytes = SESSION_FILE.read_bytes()
    # Strip the binding_hash field by parsing the JSON; this way writing
    # the binding back into the file does not change the recomputed hash.
    try:
        payload = json.loads(raw_bytes)
    except json.JSONDecodeError:
        # Corrupted or partial write; use raw bytes as fingerprint.
        return hashlib.sha256(raw_bytes).hexdigest()[:16]
    payload.pop("binding_hash", None)
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def create_session() -> int:
    """Create a fresh session file and return exit code 0 on success."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(
        json.dumps(
            {
                "created_at": int(time.time()),
                "expires_at": int(time.time()) + TTL_SECONDS,
                "pid": os.getpid(),
                "user": os.environ.get("USERNAME") or os.environ.get("USER", "unknown"),
                "platform": platform.system(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    binding = compute_binding_hash()
    # Patch binding into the freshly created payload so future --check is strict.
    payload = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    payload["binding_hash"] = binding
    SESSION_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ Session created: {SESSION_FILE}")
    print(f"   binding_hash: {binding}")
    print(f"   expires_at:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(payload['expires_at']))}")
    print(f"   TTL:          {TTL_SECONDS // 3600}h")
    return 0


def check_session() -> int:
    """Verify session exists, not expired, and binding hash matches.

    Returns 0 if valid, 1 if missing/expired/tampered.
    """
    if not SESSION_FILE.exists():
        print(f"❌ Session missing: {SESSION_FILE}")
        print("   Run: python scripts/bootstrap/check_session_active.py --create")
        return 1

    try:
        payload = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"❌ Session corrupted: {e}")
        print("   Run: python scripts/bootstrap/check_session_active.py --create")
        return 1

    now = int(time.time())
    if now > payload.get("expires_at", 0):
        print(f"❌ Session expired (expired at: "
              f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(payload['expires_at']))})")
        print("   Run: python scripts/bootstrap/check_session_active.py --create")
        return 1

    try:
        current_binding = compute_binding_hash()
    except OSError as e:
        print(f"❌ Cannot read session file: {e}")
        return 1

    expected_binding = payload.get("binding_hash", "")
    if not expected_binding:
        # First-time check: store the binding so future checks detect tampering.
        payload["binding_hash"] = current_binding
        SESSION_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"✅ Session valid (binding established): {current_binding}")
        return 0

    if current_binding != expected_binding:
        print(f"❌ Session tampered (binding mismatch):")
        print(f"   expected: {expected_binding}")
        print(f"   actual:   {current_binding}")
        return 1

    remaining = payload["expires_at"] - now
    print(f"✅ Session valid: binding={current_binding}, "
          f"remaining={remaining // 3600}h{(remaining % 3600) // 60}m")
    return 0


def destroy_session() -> int:
    """Remove the session file (used by gaf-commit --logout etc.)."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
        print(f"✅ Session destroyed: {SESSION_FILE}")
    else:
        print(f"ℹ️  Session not present: {SESSION_FILE}")
    return 0


def show_session() -> int:
    """Print the current session payload (for debugging)."""
    if not SESSION_FILE.exists():
        print(f"❌ Session missing: {SESSION_FILE}")
        return 1
    payload = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    binding = compute_binding_hash()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"current_binding: {binding}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GAF cross-platform session active binding")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--create", action="store_true", help="Create a fresh session")
    group.add_argument("--check", action="store_true", help="Verify current session")
    group.add_argument("--destroy", action="store_true", help="Remove session file")
    group.add_argument("--show", action="store_true", help="Print session payload")
    args = parser.parse_args()

    if args.create:
        return create_session()
    if args.check:
        return check_session()
    if args.destroy:
        return destroy_session()
    if args.show:
        return show_session()
    return 1


if __name__ == "__main__":
    sys.exit(main())
