"""Scan for empty folders and empty files in the project.

Used by the monthly health check (category N: Project Hygiene).

Usage:
    conda run -n gaf python scripts/scan_empty.py [root_dir]

If root_dir is not provided, scans the current working directory.
"""
import os
import sys

EXCLUDE_DIRS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build',
    '.trae', '.opencode', '.skills', '.cache', 'staticfiles', '.pytest_cache', '.ruff_cache',
    'migrations', '.trash', '.ai-memory', '__tests__', '__pycache__',
}
# Files that are intentionally empty (scaffold/placeholder convention)
EXCLUDE_EMPTY_FILES = {
    '__init__.py', '.gitkeep', '.keep', '.npmignore', 'LICENSE', 'README.md',
}


def scan(root):
    """Scan for empty directories and empty files under root."""
    empty_dirs = []
    empty_files = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Filter out excluded dirs in-place (prunes the walk)
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

        # Check for empty directories (no files and no subdirs)
        if not filenames and not dirnames:
            rel = os.path.relpath(dirpath, root)
            if rel != '.':
                empty_dirs.append(rel)

        # Check for empty files
        for fname in filenames:
            if fname in EXCLUDE_EMPTY_FILES:
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                if os.path.getsize(fpath) == 0:
                    rel = os.path.relpath(fpath, root)
                    empty_files.append(rel)
            except OSError:
                pass

    return empty_dirs, empty_files


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    empty_dirs, empty_files = scan(root)

    print("=== Empty Directories ===")
    if empty_dirs:
        for d in sorted(empty_dirs):
            print(f"  {d}")
        print(f"\nTotal: {len(empty_dirs)} empty directories")
    else:
        print("  None found")

    print("\n=== Empty Files ===")
    if empty_files:
        for f in sorted(empty_files):
            print(f"  {f}")
        print(f"\nTotal: {len(empty_files)} empty files")
    else:
        print("  None found")

    # Exit code: 0 if no issues, 1 if empty dirs/files found
    return 1 if (empty_dirs or empty_files) else 0


if __name__ == '__main__':
    sys.exit(main())
