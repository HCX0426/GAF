"""Tests for ``scripts/lessons/bypass_weekly_review.py`` (M2.F)."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.lessons.bypass_weekly_review import (
    load_bypasses,
    parse_audit_line,
    summarize_bypasses,
    update_bypass_patterns,
)

pytestmark = pytest.mark.unit


SAMPLE_LINE = (
    "BYPASS ts=2026-06-15T18:57:59Z user=alice@example.com "
    "reason=sync hook bug args=git commit --no-verify -m fix"
)


def test_parse_audit_line_valid():
    """A valid BYPASS line is parsed into its components."""
    record = parse_audit_line(SAMPLE_LINE)
    assert record is not None
    assert record["ts"] == "2026-06-15T18:57:59Z"
    assert record["user"] == "alice@example.com"
    assert record["reason"] == "sync hook bug"
    assert record["args"] == "git commit --no-verify -m fix"


def test_parse_audit_line_ignores_non_bypass():
    """Non-BYPASS lines return None."""
    assert parse_audit_line("COMMIT 12345 args=foo") is None
    assert parse_audit_line("") is None
    assert parse_audit_line("BYPASS ts=bad") is None


def test_parse_audit_line_reason_with_spaces():
    """Reasons containing spaces are captured until ``args=``."""
    line = (
        "BYPASS ts=2026-06-15T18:57:59Z user=bob reason=sync hook rolled back "
        "args=git commit --no-verify"
    )
    record = parse_audit_line(line)
    assert record["reason"] == "sync hook rolled back"
    assert record["args"] == "git commit --no-verify"


def test_load_bypasses_filters_by_window():
    """Only records within the sliding window are returned."""
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
        now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
        old = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        f.write(f"BYPASS ts={old} user=u reason=old args=git commit\n")
        f.write(f"BYPASS ts={recent} user=u reason=recent args=git commit\n")
        log_path = Path(f.name)

    try:
        bypasses = load_bypasses(log_path, days=7, now=now)
        assert len(bypasses) == 1
        assert bypasses[0][1]["reason"] == "recent"
    finally:
        log_path.unlink(missing_ok=True)


def test_summarize_bypasses_orders_by_count():
    """Top reasons are ordered by frequency descending."""
    now = datetime.now(timezone.utc)
    records = [
        (now, {"reason": "hook bug"}),
        (now, {"reason": "hook bug"}),
        (now, {"reason": "sync issue"}),
    ]
    top = summarize_bypasses(records, top_n=2)
    assert top == [("hook bug", 2), ("sync issue", 1)]


def test_update_bypass_patterns_appends_section(tmp_path):
    """The review section is appended to the output file."""
    output = tmp_path / "bypass-patterns.md"
    output.write_text("# Header\n", encoding="utf-8")
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
    bypasses = [(now, {"reason": "r1"})]
    top = [("r1", 1)]

    section = update_bypass_patterns(output, bypasses, top, days=7, now=now)
    assert "每周复盘" in section
    assert "r1" in section

    content = output.read_text(encoding="utf-8")
    assert "# Header" in content
    assert "每周复盘" in content


def test_update_bypass_patterns_dry_run_does_not_write(tmp_path):
    """Dry-run mode does not modify the output file."""
    output = tmp_path / "bypass-patterns.md"
    output.write_text("# Header\n", encoding="utf-8")
    now = datetime.now(timezone.utc)

    update_bypass_patterns(output, [], [], days=7, now=now, dry_run=True)
    assert output.read_text(encoding="utf-8") == "# Header\n"


def test_load_bypasses_tolerates_garbage_lines():
    """Malformed lines and non-UTF8 bytes do not crash parsing."""
    # Use a dynamic timestamp within the 30-day window so the test does not
    # rot as the calendar advances (hardcoded 2026-06-15 falls outside the
    # window once enough time elapses).
    recent_ts = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
        f.write(f"BYPASS ts={recent_ts} user=u reason=ok args=git\n".encode("utf-8"))
        f.write(b"not a bypass line\n")
        f.write(b"\xff\xfe garbage bytes\n")
        log_path = Path(f.name)

    try:
        bypasses = load_bypasses(log_path, days=30)
        assert len(bypasses) == 1
        assert bypasses[0][1]["reason"] == "ok"
    finally:
        log_path.unlink(missing_ok=True)
