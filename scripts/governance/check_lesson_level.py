"""check_lesson_level.py — 自动判定教训等级 (L0 vs L1)

基于 topic 内容和 cross-system 标志, 自动判定教训应归为 L0 (项目专属) 还是 L1 (跨系统可复用),
并对 L1 进一步划分子等级 (low / medium / high).

Usage:
    python scripts/governance/check_lesson_level.py --topic "conda 环境未激活"
    python scripts/governance/check_lesson_level.py --topic "API 契约变更" --cross-system
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

HIGH_IMPACT_KEYWORDS = [
    "core", "system", "architecture", "platform", "infrastructure",
    "security", "data", "model", "agent", "orchestration",
    "core", "security", "auth", "authentication", "authorization",
    "performance", "race", "concurrency", "deadlock",
]

MEDIUM_IMPACT_KEYWORDS = [
    "workflow", "process", "integration", "api", "contract",
    "deployment", "sync", "migration", "pipeline", "url",
    "serializer", "view", "routing", "config", "settings",
    "env", "environment", "docker", "nginx", "celery",
    "playwright", "test", "e2e", "fixture",
]


def _estimate_sub_level(topic: str) -> str:
    """Estimate L1 sub-level based on topic content."""
    topic_lower = topic.lower()

    for kw in HIGH_IMPACT_KEYWORDS:
        if kw in topic_lower:
            return "high"

    for kw in MEDIUM_IMPACT_KEYWORDS:
        if kw in topic_lower:
            return "medium"

    if len(topic) <= 10:
        return "low"

    return "medium"


def _build_reasoning(topic: str, cross_system: bool, sub_level: str) -> str:
    """Build human-readable reasoning string."""
    if cross_system:
        reasoning = f"topic '{topic}' involves cross-system contract, reusable experience"
    else:
        reasoning = f"topic '{topic}' is project-specific, not directly reusable"

    if cross_system:
        reasoning += f", sub-level: {sub_level} impact"

    return reasoning


def _promotion_target(level: str, sub_level: str) -> str:
    """Determine where the lesson should be promoted to."""
    if level == "L0":
        return "lessons/L0-reference (project-specific, no promotion needed)"

    targets = ["cheatsheet.md"]
    if sub_level in ("medium", "high"):
        targets.append("lessons/L3-reference")
    if sub_level == "high":
        targets.append("ai-operating-handbook.md")

    return " + ".join(targets)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="自动判定教训等级 (L0 vs L1)"
    )
    parser.add_argument(
        "--topic",
        required=True,
        help="教训主题描述",
    )
    parser.add_argument(
        "--cross-system",
        action="store_true",
        default=False,
        help="是否涉及跨系统可复用的契约/模式",
    )
    args = parser.parse_args(argv)

    topic = args.topic
    cross_system = args.cross_system

    if cross_system:
        level = "L1"
        sub_level = _estimate_sub_level(topic)
    else:
        level = "L0"
        sub_level = "N/A"

    reasoning = _build_reasoning(topic, cross_system, sub_level)
    promotion_target = _promotion_target(level, sub_level)

    result: dict[str, Any] = {
        "level": level,
        "sub_level": sub_level,
        "reasoning": reasoning,
        "promotion_target": promotion_target,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())