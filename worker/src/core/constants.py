"""Consolidated enums shared across agent modules.

This module is the single source of truth for status/type/operator
enums used by string-literal comparisons throughout worker/src/. Phase 1
(spec-40) introduces the module and dedups ComparisonOperator/LoopType/
NodeType. Phase 2 (spec-44) migrates the remaining 80+ string literals
to these enums.

Design note: enums inherit from ``str`` so they compare equal to their
string values (``ComparisonOperator.EQ == "eq"`` is True). This enables
gradual migration — call sites that still pass raw strings work
unchanged when compared against the enum.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class ComparisonOperator(StrEnum):
    """Comparison operators used by BranchNode + while-loop evaluation.

    Duplicated in engine.py:_evaluate_loop_condition and
    nodes/branch.py:BranchNode._evaluate before spec-40 Phase 2.
    Now consolidated here as the single source of truth.
    """

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    CONTAINS = "contains"


class LoopType(StrEnum):
    """Loop types used by LoopNode + PipelineEngine._loop_should_continue.

    Duplicated as raw string literals in engine.py:784,788 and
    nodes/loop.py:77,90 before spec-40 Phase 2.
    """

    FOR = "for"
    WHILE = "while"


class NodeType(StrEnum):
    """Pipeline node types.

    Used by PipelineEngine._resolve_next_node + debug_image_saver +
    structured_logger. Phase 1 only defines the enum; Phase 2 (spec-44)
    migrates call sites.
    """

    BRANCH = "branch"
    GOTO = "goto"
    LOOP = "loop"
    CLICK = "click"
    SWIPE = "swipe"
    LONG_PRESS = "long_press"
    TEMPLATE_MATCH = "template_match"


def evaluate_comparison(actual: Any, operator: Any, expected: Any) -> bool:
    """Single source of truth for comparison evaluation.

    Replaces the duplicated logic in engine.py:_evaluate_loop_condition
    and nodes/branch.py:BranchNode._evaluate. Both call sites now use
    this function (spec-40 Phase 2).

    Args:
        actual: Current value of the condition variable.
        operator: ComparisonOperator enum, its string value, or any
            string. Unknown values fall back to equality comparison
            (preserves existing BranchNode._evaluate else-branch behavior).
        expected: Configured comparison value.

    Returns:
        Comparison result. On TypeError/ValueError (e.g., comparing
        non-numeric values with gt/lt/gte/lte) returns False — matching
        the original try/except behavior in both duplicated call sites.
    """
    # Normalize operator to ComparisonOperator enum if possible.
    if isinstance(operator, ComparisonOperator):
        op = operator
    else:
        try:
            op = ComparisonOperator(operator)
        except ValueError:
            # Unknown operator — preserve original fallback to equality.
            return actual == expected

    try:
        if op is ComparisonOperator.EQ:
            return actual == expected
        if op is ComparisonOperator.NEQ:
            return actual != expected
        if op is ComparisonOperator.GT:
            return float(actual) > float(expected)
        if op is ComparisonOperator.LT:
            return float(actual) < float(expected)
        if op is ComparisonOperator.GTE:
            return float(actual) >= float(expected)
        if op is ComparisonOperator.LTE:
            return float(actual) <= float(expected)
        if op is ComparisonOperator.CONTAINS:
            return str(expected) in str(actual)
    except (TypeError, ValueError):
        return False
    # Unreachable — op is bound to one of the 7 ComparisonOperator values.
    return False


class ServerStatus(StrEnum):
    """Server message status types (handler.py:165 etc.).

    Used by agent ws_client to parse server JSON payloads where
    ``status`` field indicates message category.
    """
    ERROR = "error"
    INFO = "info"
    WARNING = "warning"
    SUCCESS = "success"


class EventType(StrEnum):
    """Recording event types (recording_to_pipeline.py etc.).

    Used by StepRecorder to categorize user input events during
    recording sessions.
    """
    CLICK = "click"
    KEY = "key"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    SWIPE = "swipe"
    LONG_PRESS = "long_press"


class WorkerStatus(StrEnum):
    """Worker status values (health_checker.py:535 etc.).

    Mirrors backend workers.models.Worker.Status choices.
    Used by agent health checker to parse ADB device state strings.
    """
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    IDLE = "idle"
