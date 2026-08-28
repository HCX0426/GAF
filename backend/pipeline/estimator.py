"""
Pipeline 执行时间预估器
基于每种节点类型的默认耗时基准值计算 Pipeline 总耗时
"""
from collections import Counter

DEFAULT_NODE_DURATIONS: dict[str, int] = {
    'click': 200,
    'swipe': 800,
    'key_press': 150,
    'text_input': 3000,
    'template_match': 1500,
    'ocr': 2500,
    'color_detect': 500,
    'feature_match': 2000,
    'wait': 3000,
    'branch': 50,
    'loop': 1000,
    'random_delay': 1000,
    'notify': 500,
    'device_control': 2000,
    'monitor': 100,
    'sub_pipeline': 30000,
    'goto': 10,
    'login_account': 5000,
    'switch_account': 3000,
    'switch_resource': 2000,
    'captcha_detect': 1000,
}


class PipelineTimeEstimator:
    """
    Pipeline 执行时间预估

    算法：
    1. 统计每种 node_type 出现次数
    2. 对有历史数据的类型使用历史均值；无历史数据使用 DEFAULT_NODE_DURATIONS
    3. total = sum(count × avg_ms) × 修正系数 1.1
    """

    CORRECTION_FACTOR = 1.1

    def estimate(self, graph_data: dict) -> dict:
        """
        预估 Pipeline 总执行时间。

        返回: { total_ms, breakdown: [{ node_type, count, avg_ms, total_ms }] }
        """
        nodes = graph_data.get('nodes', [])
        type_counter = Counter(
            (node.get('node_type') or node.get('type') or 'unknown') for node in nodes
        )

        breakdown = []
        total_ms = 0

        for node_type, count in type_counter.items():
            avg_ms = DEFAULT_NODE_DURATIONS.get(node_type, 5000)
            item_total = int(count * avg_ms)

            if node_type == 'wait':
                for node in nodes:
                    if (node.get('node_type') or node.get('type')) == 'wait':
                        data = node.get('data', {}) or {}
                        timeout = data.get('timeout', 3000)
                        item_total += max(0, int(timeout) - 3000)

            if node_type == 'loop':
                for node in nodes:
                    if (node.get('node_type') or node.get('type')) == 'loop':
                        data = node.get('data', {}) or {}
                        max_iter = data.get('maxIterations', 1)
                        item_total += (max_iter - 1) * 2000

            breakdown.append({
                'node_type': node_type,
                'count': count,
                'avg_ms': avg_ms,
                'total_ms': item_total,
            })
            total_ms += item_total

        total_ms = int(total_ms * self.CORRECTION_FACTOR)

        return {
            'total_ms': total_ms,
            'breakdown': breakdown,
        }
