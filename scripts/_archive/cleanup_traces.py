#!/usr/bin/env python3

from pathlib import Path
import json
import datetime


TRACES_DIR = Path(".ai-memory/session-traces")
SUMMARY_FILE = ".trace-summary.md"
KEEP_NEWEST = 20
COMPRESS_MAX = 100


def load_traces():
    if not TRACES_DIR.exists():
        return []
    files = sorted(
        [f for f in TRACES_DIR.iterdir() if f.is_file() and f.suffix == ".json"],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return files


def extract_summary(file_path):
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    task_type = data.get("task_type", "unknown")
    decisions = data.get("decision_path", [])
    if isinstance(decisions, list):
        decision_lines = [str(d)[:120] for d in decisions[:5]]
    else:
        decision_lines = [str(decisions)[:120]]
    lines = [f"- **{task_type}**"]
    lines.extend(f"  - {dl}" for dl in decision_lines)
    return "\n".join(lines)


def run():
    files = load_traces()
    if not files:
        print("[cleanup_traces] No trace files found.")
        return

    kept = files[:KEEP_NEWEST]
    to_compress = files[KEEP_NEWEST:COMPRESS_MAX]
    to_delete = files[COMPRESS_MAX:]

    print(f"[cleanup_traces] Total traces: {len(files)}")
    print(f"  Kept (newest {KEEP_NEWEST}):  {len(kept)}")
    print(f"  Compressed ({KEEP_NEWEST}-{COMPRESS_MAX}): {len(to_compress)}")
    print(f"  Deleted (>{COMPRESS_MAX}):    {len(to_delete)}")

    if to_compress:
        summary_path = TRACES_DIR / SUMMARY_FILE
        existing = ""
        if summary_path.exists():
            existing = summary_path.read_text(encoding="utf-8")
        new_entries = []
        for f in to_compress:
            summary = extract_summary(f)
            if summary:
                new_entries.append(summary)
                f.unlink()
        if new_entries:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            header = f"# Session Trace Summary\n\n_Generated: {timestamp}_\n\n"
            combined = header + "\n\n".join(new_entries)
            if existing:
                combined += "\n\n---\n\n" + existing
            summary_path.write_text(combined, encoding="utf-8")
            print(f"  -> Compressed {len(new_entries)} traces into {SUMMARY_FILE}")

    if to_delete:
        for f in to_delete:
            f.unlink()
        print(f"  -> Deleted {len(to_delete)} old traces")

    print("[cleanup_traces] Done.")


if __name__ == "__main__":
    run()