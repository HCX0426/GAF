"""
MaaFramework Pipeline JSON 兼容转换器

GAF Pipeline JSON 格式 → MaaFramework Pipeline JSON 格式转换

MaaFramework Pipeline 格式参考：https://maa.plus/docs/zh-cn/3.1-%E4%BB%BB%E5%8A%A1%E6%B5%81%E6%B0%B4%E7%BA%BF%E5%8D%8F%E8%AE%AE.html

GAF 格式：
  { nodes: [{ id, type, position, data: { label, config } }], edges: [{ source, target }] }

MaaFramework 格式：
  { "TaskName": { "action": "...", "next": [...], "algorithm": "...", ... } }
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

GAF_TO_MAA_ACTION_MAP: dict[str, str] = {
    'click': 'Click',
    'swipe': 'Swipe',
    'long_click': 'Click',
    'text_input': 'InputText',
    'key_event': 'PressKey',
    'start_app': 'StartApp',
    'stop_app': 'StopApp',
    'screenshot': 'Custom',
    'wait': 'Wait',
    'template_match': 'Click',
    'ocr': 'Click',
    'image_match': 'Click',
    'color_match': 'Click',
    'branch': 'Custom',
    'loop': 'Custom',
    'parallel': 'Custom',
    'monitor': 'Custom',
    'notify': 'Custom',
    'log': 'Custom',
    'script': 'Custom',
    'delay': 'Wait',
    'device_control': 'Custom',
}

GAF_TO_MAA_ALGORITHM_MAP: dict[str, str] = {
    'click': 'DirectHit',
    'swipe': 'DirectHit',
    'long_click': 'DirectHit',
    'text_input': 'DirectHit',
    'template_match': 'TemplateMatch',
    'ocr': 'OcrDetect',
    'image_match': 'FeatureMatch',
    'color_match': 'ColorMatch',
    'wait': 'DirectHit',
    'delay': 'DirectHit',
    'branch': 'DirectHit',
    'loop': 'DirectHit',
    'parallel': 'DirectHit',
    'monitor': 'DirectHit',
    'notify': 'DirectHit',
    'log': 'DirectHit',
    'script': 'DirectHit',
    'key_event': 'DirectHit',
    'start_app': 'DirectHit',
    'stop_app': 'DirectHit',
    'screenshot': 'DirectHit',
    'device_control': 'DirectHit',
}


def _gaf_node_to_maa_task(node: dict[str, Any], task_name: str) -> dict[str, Any]:
    """将单个 GAF Pipeline 节点转换为 MaaFramework 任务条目"""
    node_type = node.get('type', 'click')
    data = node.get('data', {})
    config = data.get('config', {})

    action = GAF_TO_MAA_ACTION_MAP.get(node_type, 'Custom')
    algorithm = GAF_TO_MAA_ALGORITHM_MAP.get(node_type, 'DirectHit')

    maa_task: dict[str, Any] = {
        'action': action,
        'algorithm': algorithm,
    }

    if node_type == 'template_match':
        maa_task['template'] = config.get('template', '')
        if config.get('threshold'):
            maa_task['threshold'] = float(config['threshold'])
        if config.get('roi') and isinstance(config['roi'], list) and len(config['roi']) == 4:
            maa_task['roi'] = config['roi']
        if action == 'Click':
            position = data.get('position')
            if position and isinstance(position, dict):
                maa_task['target'] = [position.get('x', 0), position.get('y', 0)]

    elif node_type in ('click', 'long_click'):
        position = config.get('position')
        if position and isinstance(position, dict):
            maa_task['target'] = [position.get('x', 0), position.get('y', 0)]
        if node_type == 'long_click':
            maa_task['hold_time'] = config.get('hold_time', 1000)

    elif node_type == 'swipe':
        begin = config.get('begin')
        end = config.get('end')
        if begin and isinstance(begin, dict):
            maa_task['begin'] = [begin.get('x', 0), begin.get('y', 0)]
        if end and isinstance(end, dict):
            maa_task['end'] = [end.get('x', 0), end.get('y', 0)]
        maa_task['duration'] = config.get('duration', 200)

    elif node_type == 'text_input':
        maa_task['input_text'] = config.get('text', '')
        position = config.get('position')
        if position and isinstance(position, dict):
            maa_task['target'] = [position.get('x', 0), position.get('y', 0)]

    elif node_type == 'key_event':
        maa_task['key'] = config.get('key', '')
        if config.get('count'):
            maa_task['count'] = int(config['count'])

    elif node_type == 'start_app' or node_type == 'stop_app':
        maa_task['package'] = config.get('package', config.get('app', ''))

    elif node_type in ('wait', 'delay'):
        maa_task['time'] = config.get('time', config.get('duration', 1000))

    elif node_type == 'ocr':
        maa_task['roi'] = config.get('roi', [0, 0, 1280, 720])
        if config.get('expected'):
            maa_task['expected'] = config['expected']
        if config.get('replace'):
            maa_task['replace'] = config['replace']

    elif node_type == 'image_match':
        if config.get('template'):
            maa_task['template'] = config['template']
        if config.get('roi'):
            maa_task['roi'] = config['roi']

    elif node_type == 'color_match':
        if config.get('color'):
            maa_task['color'] = config['color']
        if config.get('roi'):
            maa_task['roi'] = config['roi']
        if config.get('count'):
            maa_task['count'] = int(config['count'])

    elif node_type == 'monitor':
        if config.get('interval'):
            maa_task['interval'] = config['interval']
        if config.get('timeout'):
            maa_task['timeout'] = config['timeout']

    elif node_type == 'notify':
        if config.get('title'):
            maa_task['title'] = config['title']
        if config.get('content'):
            maa_task['content'] = config['content']

    elif node_type == 'script':
        if config.get('path'):
            maa_task['path'] = config['path']
        if config.get('args'):
            maa_task['args'] = config['args']

    elif node_type == 'device_control':
        if config.get('action'):
            maa_task['sub_action'] = config['action']
            if config.get('action') == 'resolution':
                maa_task['width'] = config.get('width', 1280)
                maa_task['height'] = config.get('height', 720)

    extra = data.get('extra', {})
    if extra:
        for k, v in extra.items():
            if k not in maa_task:
                maa_task[k] = v

    return maa_task


def _build_next_list(node_id: str, edges: list[dict[str, Any]]) -> list[str]:
    """根据边构建 MaaFramework next 数组"""
    next_ids = []
    for edge in edges:
        if edge.get('source') == node_id:
            target = edge.get('target', '')
            if target:
                next_ids.append(target)
    return next_ids


def gaf_pipeline_to_maa(gaf_pipeline: dict[str, Any]) -> dict[str, Any]:
    """将 GAF Pipeline JSON 转换为兼容 MaaFramework 的 Pipeline JSON

    Args:
        gaf_pipeline: GAF 格式的 Pipeline { name, nodes: [...], edges: [...] }

    Returns:
        MaaFramework 兼容格式 { "NodeId": { action, algorithm, next, ... }, ... }
    """
    nodes = gaf_pipeline.get('nodes', [])
    edges = gaf_pipeline.get('edges', [])

    maa_pipeline: dict[str, Any] = {}

    for node in nodes:
        node_id = node.get('id', '')
        if not node_id:
            continue
        task_name = node.get('data', {}).get('label', node_id)
        if not task_name:
            task_name = node_id

        maa_task = _gaf_node_to_maa_task(node, task_name)
        next_list = _build_next_list(node_id, edges)
        if next_list:
            maa_task['next'] = next_list

        maa_pipeline[node_id] = maa_task

    return maa_pipeline


def maa_pipeline_to_serializable(maa_pipeline: dict[str, Any]) -> str:
    """将 MaaFramework Pipeline 转为 JSON 字符串"""
    import json
    return json.dumps(maa_pipeline, ensure_ascii=False, indent=2)


def validate_and_convert(gaf_pipeline: dict[str, Any]) -> dict[str, Any] | None:
    """验证并转换 GAF Pipeline 为 MaaFramework 格式

    Args:
        gaf_pipeline: GAF Pipeline JSON

    Returns:
        转换后的 MaaFramework Pipeline，验证失败返回 None
    """
    if not isinstance(gaf_pipeline, dict):
        logger.warning('Pipeline 格式错误: 非 dict 类型')
        return None

    nodes = gaf_pipeline.get('nodes')
    if not nodes or not isinstance(nodes, list):
        logger.warning('Pipeline 缺少 nodes 数组')
        return None

    if len(nodes) == 0:
        logger.warning('Pipeline nodes 为空')
        return None

    edges = gaf_pipeline.get('edges')
    if edges is not None and not isinstance(edges, list):
        logger.warning('Pipeline edges 格式错误')
        return None

    try:
        maa = gaf_pipeline_to_maa(gaf_pipeline)
        return maa
    except Exception as e:
        logger.error('Pipeline 转换失败: %s', e)
        return None
