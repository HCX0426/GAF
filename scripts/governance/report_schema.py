"""report_schema.py - JSON schema dataclasses for doc_health_check reports.

Spec-41 §4.1: JSON schema for .cache/doc_health_report.json
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class Issue:
    """Single doc health issue found by a dimension check."""

    dimension: str
    severity: Literal["P0", "P1", "P2"]
    evidence: str
    suggested_fix: str
    root_cause_hint: str
    file: str | None = None
    line: int | None = None
    files: list[str] | None = None
    consumed: bool = False
    id: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self.id:
            key = f"{self.dimension}|{self.file or ''}|{self.line or 0}|{self.severity}|{self.evidence}"
            self.id = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Drop None values to keep JSON compact
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class ReportSummary:
    """Aggregate counts of issues."""

    total: int
    by_severity: dict[str, int]
    by_dimension: dict[str, int]
    # Spec-42 Phase 1: issues already consumed (patched in prior sessions).
    # Computed from Issue.consumed flags by ``from_issues``.
    consumed_count: int = 0

    @classmethod
    def from_issues(cls, issues: list[Issue]) -> "ReportSummary":
        sev_counter = Counter(i.severity for i in issues)
        dim_counter = Counter(i.dimension for i in issues)
        # Ensure all severity keys present
        for sev in ("P0", "P1", "P2"):
            sev_counter.setdefault(sev, 0)
        consumed_count = sum(1 for i in issues if i.consumed)
        return cls(
            total=len(issues),
            by_severity=dict(sev_counter),
            by_dimension=dict(dim_counter),
            consumed_count=consumed_count,
        )


@dataclass
class DocHealthReport:
    """Top-level report object written to .cache/doc_health_report.json."""

    generated_at: str
    repo_root: str
    git_sha: str
    duration_seconds: float
    summary: ReportSummary
    issues: list[Issue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "repo_root": self.repo_root,
            "git_sha": self.git_sha,
            "duration_seconds": self.duration_seconds,
            "summary": asdict(self.summary),
            "issues": [i.to_dict() for i in self.issues],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
