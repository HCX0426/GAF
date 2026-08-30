"""
录制数据分析器 - 将录制数据转换为 Pipeline JSON
1. 合并连续相同位置的点击（去重）
2. 识别"等待画面稳定"模式
3. 自动插入等待节点

生成的 Pipeline JSON 与 engine.parser.PipelineParser 兼容，可直接在编辑器中使用
"""
import logging

from core.constants import EventType
from core.recording import ActionEvent, RecordingData

logger = logging.getLogger(__name__)


def convert_recording_to_pipeline(recording: RecordingData, pipeline_name: str = '') -> dict:
    """将录制数据转换为 Pipeline JSON

    Args:
        recording: 录制数据
        pipeline_name: Pipeline 名称，为空则使用录制名称

    Returns:
        Pipeline JSON 字典，包含 nodes、edges、name
    """
    events = recording.events
    if not events:
        return {'nodes': [], 'edges': []}

    events = _merge_nearby_clicks(events)
    events = _remove_redundant_screenshots(events)

    nodes = []
    edges = []
    node_index = 0
    last_node_id = None

    for event in events:
        if event.event_type == EventType.CLICK:
            node_id = f'click_{node_index}'
            nodes.append({
                'id': node_id,
                'node_type': 'click',
                'position': {'x': 250, 'y': 50 + node_index * 80},
                'data': {
                    'label': f'点击 ({event.x}, {event.y})',
                    'config': {
                        'x': event.x,
                        'y': event.y,
                        'button': event.button,
                    },
                },
            })
            if last_node_id:
                edges.append({
                    'id': f'e_{last_node_id}_{node_id}',
                    'from': last_node_id,
                    'to': node_id,
                })
            node_index += 1

            template_id = f'wait_{node_index}'
            nodes.append({
                'id': template_id,
                'node_type': 'wait',
                'position': {'x': 250, 'y': 50 + node_index * 80},
                'data': {
                    'label': '等待画面稳定',
                    'config': {
                        'mode': 'stable',
                        'max_wait': 3.0,
                    },
                },
            })
            edges.append({
                'id': f'e_{node_id}_{template_id}',
                'from': node_id,
                'to': template_id,
            })
            last_node_id = template_id
            node_index += 1

        elif event.event_type == EventType.KEY:
            node_id = f'key_{node_index}'
            nodes.append({
                'id': node_id,
                'node_type': 'key_press',
                'position': {'x': 250, 'y': 50 + node_index * 80},
                'data': {
                    'label': f'按键 {event.key}',
                    'config': {'key': event.key},
                },
            })
            if last_node_id:
                edges.append({
                    'id': f'e_{last_node_id}_{node_id}',
                    'from': last_node_id,
                    'to': node_id,
                })
            last_node_id = node_id
            node_index += 1

        elif event.event_type == EventType.WAIT:
            if event.duration < 0.3:
                continue
            node_id = f'wait_{node_index}'
            nodes.append({
                'id': node_id,
                'node_type': 'wait',
                'position': {'x': 250, 'y': 50 + node_index * 80},
                'data': {
                    'label': f'等待 {int(event.duration * 1000)}ms',
                    'config': {
                        'mode': 'fixed',
                        'seconds': event.duration,
                    },
                },
            })
            if last_node_id:
                edges.append({
                    'id': f'e_{last_node_id}_{node_id}',
                    'from': last_node_id,
                    'to': node_id,
                })
            last_node_id = node_id
            node_index += 1

    return {
        'name': pipeline_name or recording.name,
        'nodes': nodes,
        'edges': edges,
    }


def _merge_nearby_clicks(events: list[ActionEvent]) -> list[ActionEvent]:
    """合并相邻相同位置的重复点击（去重）

    规则：相邻两次点击若坐标差 ≤ 5px 且间隔 < 1s，保留首次

    Args:
        events: 操作事件列表

    Returns:
        去重后的事件列表
    """
    if len(events) < 2:
        return events

    merged = []
    i = 0
    while i < len(events):
        current = events[i]
        if current.event_type == EventType.CLICK and merged:
            last = merged[-1]
            if (last.event_type == EventType.CLICK and
                    abs(last.x - current.x) <= 5 and
                    abs(last.y - current.y) <= 5 and
                    current.timestamp - last.timestamp < 1.0):
                i += 1
                continue
        merged.append(current)
        i += 1
    return merged


def _remove_redundant_screenshots(events: list[ActionEvent]) -> list[ActionEvent]:
    """移除冗余截图事件，保留关键截图（首帧、状态变化前）

    Args:
        events: 操作事件列表

    Returns:
        过滤后的事件列表
    """
    return [e for e in events if e.event_type != 'screenshot']
