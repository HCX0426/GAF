"""Convert recording data to Pipeline JSON.

This module mirrors worker/src/core/recording_to_pipeline.py so the backend
can convert recordings without spawning an agent subprocess.

P-008: migrated from tasks app — Recording conversion is a pipeline-app
concern (Recording → Pipeline generation), so the converter belongs here.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _merge_nearby_clicks(events: list[dict]) -> list[dict]:
    """Merge clicks at the same position within 1 second."""
    if not events:
        return []
    merged: list[dict] = []
    for event in events:
        if event.get("event_type") != "click":
            merged.append(event)
            continue
        if merged and merged[-1].get("event_type") == "click":
            last = merged[-1]
            dx = abs(last.get("x", 0) - event.get("x", 0))
            dy = abs(last.get("y", 0) - event.get("y", 0))
            dt = abs(last.get("timestamp", 0) - event.get("timestamp", 0))
            if dx <= 5 and dy <= 5 and dt < 1.0:
                continue  # Skip duplicate click
        merged.append(event)
    return merged


def _remove_redundant_screenshots(events: list[dict]) -> list[dict]:
    """Remove consecutive screenshot events (keep only the first in a burst)."""
    result: list[dict] = []
    for event in events:
        if event.get("event_type") == "screenshot" and result and result[-1].get("event_type") == "screenshot":
            continue  # Skip consecutive screenshot
        result.append(event)
    return result


def convert_recording_to_pipeline(recording_data: dict, pipeline_name: str = "") -> dict[str, Any]:
    """Convert recording data dict to Pipeline JSON.

    Args:
        recording_data: Recording data dict with 'events' list.
        pipeline_name: Optional pipeline name.

    Returns:
        Pipeline JSON dict with 'name', 'nodes', 'edges'.
    """
    events = recording_data.get("events", [])
    if not events:
        return {
            "name": pipeline_name or recording_data.get("name", "录制导入"),
            "nodes": [],
            "edges": [],
        }

    events = _merge_nearby_clicks(events)
    events = _remove_redundant_screenshots(events)

    nodes: list[dict] = []
    edges: list[dict] = []
    node_index = 0
    last_node_id: str | None = None

    for event in events:
        event_type = event.get("event_type")

        if event_type == "click":
            node_id = f"click_{node_index}"
            nodes.append({
                "id": node_id,
                "type": "click",
                "position": {"x": 250, "y": 50 + node_index * 80},
                "data": {
                    "label": f"点击 ({event.get('x', 0)}, {event.get('y', 0)})",
                    "config": {
                        "x": event.get("x", 0),
                        "y": event.get("y", 0),
                        "button": event.get("button", "left"),
                    },
                },
            })
            if last_node_id:
                edges.append({"id": f"e_{last_node_id}_{node_id}", "source": last_node_id, "target": node_id})
            node_index += 1

            # Auto-insert wait node after click
            wait_id = f"wait_{node_index}"
            nodes.append({
                "id": wait_id,
                "type": "wait",
                "position": {"x": 250, "y": 50 + node_index * 80},
                "data": {"label": "等待画面稳定", "config": {"mode": "stable", "max_wait": 3.0}},
            })
            edges.append({"id": f"e_{node_id}_{wait_id}", "source": node_id, "target": wait_id})
            last_node_id = wait_id
            node_index += 1

        elif event_type == "key":
            node_id = f"key_{node_index}"
            nodes.append({
                "id": node_id,
                "type": "key_press",
                "position": {"x": 250, "y": 50 + node_index * 80},
                "data": {"label": f"按键 {event.get('key', '')}", "config": {"key": event.get("key", "")}},
            })
            if last_node_id:
                edges.append({"id": f"e_{last_node_id}_{node_id}", "source": last_node_id, "target": node_id})
            last_node_id = node_id
            node_index += 1

        elif event_type == "wait":
            duration = event.get("duration", 0)
            if duration < 0.3:
                continue
            node_id = f"wait_{node_index}"
            nodes.append({
                "id": node_id,
                "type": "wait",
                "position": {"x": 250, "y": 50 + node_index * 80},
                "data": {"label": f"等待 {int(duration * 1000)}ms", "config": {"mode": "fixed", "seconds": duration}},
            })
            if last_node_id:
                edges.append({"id": f"e_{last_node_id}_{node_id}", "source": last_node_id, "target": node_id})
            last_node_id = node_id
            node_index += 1

        elif event_type == "swipe":
            # Swipe event: x1/y1 → x2/y2 over `duration` (ms). Mirrors
            # SwipeNode config schema (x1/y1/x2/y2/duration/steps).
            node_id = f"swipe_{node_index}"
            x1 = event.get("x1", event.get("x", 0))
            y1 = event.get("y1", event.get("y", 0))
            x2 = event.get("x2", event.get("end_x", x1))
            y2 = event.get("y2", event.get("end_y", y1))
            duration_ms = int(event.get("duration", event.get("duration_ms", 300)))
            nodes.append({
                "id": node_id,
                "type": "swipe",
                "position": {"x": 250, "y": 50 + node_index * 80},
                "data": {
                    "label": f"滑动 ({x1},{y1}) → ({x2},{y2})",
                    "config": {
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                        "duration": duration_ms, "steps": 10,
                    },
                },
            })
            if last_node_id:
                edges.append({"id": f"e_{last_node_id}_{node_id}", "source": last_node_id, "target": node_id})
            last_node_id = node_id
            node_index += 1

        elif event_type == "long_press":
            # LongPress event: x/y held for `duration` (ms). Mirrors
            # LongPressNode config schema (x/y/button/duration_ms).
            node_id = f"long_press_{node_index}"
            x = event.get("x", 0)
            y = event.get("y", 0)
            duration_ms = int(event.get("duration", event.get("duration_ms", 1000)))
            button = event.get("button", "left")
            nodes.append({
                "id": node_id,
                "type": "long_press",
                "position": {"x": 250, "y": 50 + node_index * 80},
                "data": {
                    "label": f"长按 ({x},{y}) {duration_ms}ms",
                    "config": {
                        "x": x, "y": y, "button": button,
                        "duration_ms": duration_ms,
                    },
                },
            })
            if last_node_id:
                edges.append({"id": f"e_{last_node_id}_{node_id}", "source": last_node_id, "target": node_id})
            last_node_id = node_id
            node_index += 1

        elif event_type == "text_input":
            # TextInput event: text string. Mirrors TextInputNode config
            # schema (text/interval/clear_before).
            node_id = f"text_input_{node_index}"
            text = event.get("text", "")
            nodes.append({
                "id": node_id,
                "type": "text_input",
                "position": {"x": 250, "y": 50 + node_index * 80},
                "data": {
                    "label": f"输入 {text[:20]}{'…' if len(text) > 20 else ''}",
                    "config": {
                        "text": text,
                        "interval": 0.02,
                        "clear_before": False,
                    },
                },
            })
            if last_node_id:
                edges.append({"id": f"e_{last_node_id}_{node_id}", "source": last_node_id, "target": node_id})
            last_node_id = node_id
            node_index += 1

    return {
        "name": pipeline_name or recording_data.get("name", "录制导入"),
        "nodes": nodes,
        "edges": edges,
    }
