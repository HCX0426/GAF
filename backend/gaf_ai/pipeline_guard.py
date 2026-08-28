"""TD-390: LLM 生成 Pipeline 的静态守门 + 风险评分。

在 `generate_pipeline` 把 graph_data 交付前端执行前，做一层不依赖真实设备的
静态校验（结构 / 循环 / 坐标边界 / 风险分级），让前端对高风险生成物弹确认。
执行侧超时熔断/回退属 PipelineEngine 范畴，不在本模块。
"""
from typing import Any

# 节点风险分级（按副作用严重性）
SAFE_NODE_TYPES = {
    'init', 'start', 'end', 'screenshot', 'ocr', 'template_match', 'wait',
    'condition', 'branch', 'loop', 'delay', 'log', 'analyze', 'nop',
}
MEDIUM_NODE_TYPES = {
    'click', 'input_text', 'swipe', 'key_press', 'long_press', 'scroll',
    'double_click', 'drag',
}
HIGH_NODE_TYPES = {
    'shell_command', 'adb_command', 'restart', 'install', 'uninstall',
    'file_operation', 'kill', 'broadcast', 'start_activity', 'api_call',
    'write_file', 'update_config', 'execute_skill', 'send_intent',
}

# 坐标类参数键（可能越界）
COORD_KEYS = {'x', 'y', 'left', 'top', 'width', 'height'}
MAX_COORD = 4096  # 宽松上界，超此即视为异常


def _has_cycle(adj: dict[str, list[str]]) -> bool:
    """基于邻接表判环（DFS 三色标记）。"""
    white, gray, black = 0, 1, 2
    color = dict.fromkeys(adj, white)

    def dfs(node: str) -> bool:
        color[node] = gray
        for nxt in adj.get(node, []):
            if color.get(nxt, white) == gray:
                return True
            if color.get(nxt, white) == white and dfs(nxt):
                return True
        color[node] = black
        return False

    return any(color[nid] == white and dfs(nid) for nid in adj)


def _reachable(adj: dict[str, list[str]], start: str) -> set[str]:
    """从 start DFS 可达节点集合。"""
    seen: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(adj.get(cur, []))
    return seen


def validate_and_score(graph_data: Any) -> dict:
    """对 LLM 生成的 graph_data 做静态守门 + 风险评分。

    返回结构见 spec; valid 为 False 时 errors 非空。
    """
    errors: list[str] = []
    warnings: list[str] = []
    high_risk_nodes: list[str] = []
    risk_score = 0

    if not isinstance(graph_data, dict):
        errors.append('graph_data 必须是对象')
        return _result(False, errors, warnings, 0, 'high', [], True, [])

    nodes = graph_data.get('nodes')
    if not isinstance(nodes, list) or not nodes:
        errors.append('nodes 缺失或为空')
        return _result(False, errors, warnings, 0, 'high', [], False, [])

    node_ids: list[str] = []
    seen: set[str] = set()
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f'nodes[{i}] 不是对象')
            continue
        nid = node.get('id') or node.get('node_id')
        if not nid:
            errors.append(f'nodes[{i}] 缺少 id')
            continue
        if nid in seen:
            errors.append(f'重复节点 id: {nid}')
        seen.add(nid)
        node_ids.append(nid)

        ntype = node.get('node_type')
        if not ntype:
            warnings.append(f'节点 {nid} 缺少 node_type')
            continue
        if ntype in HIGH_NODE_TYPES:
            high_risk_nodes.append(nid)
            risk_score += 3
        elif ntype in MEDIUM_NODE_TYPES:
            risk_score += 1
        elif ntype not in SAFE_NODE_TYPES:
            warnings.append(f'未知 node_type: {ntype}（按安全处理，建议人工确认）')

        for key in COORD_KEYS:
            val = node.get(key)
            if isinstance(val, (int, float)) and not isinstance(val, bool) and (val < 0 or val > MAX_COORD):
                warnings.append(f'节点 {nid} 坐标 {key}={val} 超出合理范围 [0, {MAX_COORD}]')

    # 边：引用完整性 + 邻接表
    edges = graph_data.get('edges') or []
    adj = {nid: [] for nid in node_ids}
    if isinstance(edges, list):
        for e in edges:
            if not isinstance(e, dict):
                continue
            src = e.get('source') or e.get('from')
            tgt = e.get('target') or e.get('to')
            if src in adj and tgt in node_ids and src != tgt:
                adj[src].append(tgt)
            else:
                warnings.append(f'边引用了不存在的节点: {src} -> {tgt}')
    elif edges:
        warnings.append('edges 格式异常（应为列表）')

    cycle_detected = _has_cycle(adj)
    if cycle_detected:
        errors.append('检测到节点循环（可能无限执行）')

    unreachable_nodes: list[str] = []
    if node_ids:
        reachable = _reachable(adj, node_ids[0])
        unreachable_nodes = [nid for nid in node_ids if nid not in reachable]
        if unreachable_nodes:
            warnings.append(f'不可达孤立节点: {unreachable_nodes}')

    valid = len(errors) == 0
    risk_level = (
        'high' if (high_risk_nodes or cycle_detected) else
        'medium' if risk_score >= 1 else 'low'
    )
    return _result(
        valid, errors, warnings, risk_score, risk_level,
        high_risk_nodes, cycle_detected, unreachable_nodes,
    )


def _result(valid, errors, warnings, risk_score, risk_level,
            high_risk_nodes, cycle_detected, unreachable_nodes) -> dict:
    return {
        'valid': valid,
        'errors': errors,
        'warnings': warnings,
        'risk_score': risk_score,
        'risk_level': risk_level,
        'high_risk_nodes': high_risk_nodes,
        'cycle_detected': cycle_detected,
        'unreachable_nodes': unreachable_nodes,
    }
