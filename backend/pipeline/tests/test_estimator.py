"""Tests for pipeline.estimator.PipelineTimeEstimator (pure logic, no DB).

Estimation algorithm:
1. Count each node.type occurrence.
2. avg_ms = DEFAULT_NODE_DURATIONS[type] or 5000 (unknown).
3. wait nodes: add max(0, timeout - 3000) per node.
4. loop nodes: add (maxIterations - 1) * 2000 per node.
5. total = sum(item_total) * CORRECTION_FACTOR (1.1).
"""

from django.test import TestCase

from pipeline.estimator import DEFAULT_NODE_DURATIONS, PipelineTimeEstimator


class EstimateBasicTests(TestCase):
    """Basic estimation: single node types, correction factor."""

    def setUp(self):
        self.estimator = PipelineTimeEstimator()

    def test_empty_graph(self):
        result = self.estimator.estimate({'nodes': [], 'edges': []})
        self.assertEqual(result['total_ms'], 0)
        self.assertEqual(result['breakdown'], [])

    def test_empty_dict(self):
        result = self.estimator.estimate({})
        self.assertEqual(result['total_ms'], 0)
        self.assertEqual(result['breakdown'], [])

    def test_single_click_node(self):
        graph = {'nodes': [{'type': 'click'}], 'edges': []}
        result = self.estimator.estimate(graph)
        expected = int(1 * DEFAULT_NODE_DURATIONS['click'] * 1.1)
        self.assertEqual(result['total_ms'], expected)
        self.assertEqual(len(result['breakdown']), 1)
        self.assertEqual(result['breakdown'][0]['node_type'], 'click')
        self.assertEqual(result['breakdown'][0]['count'], 1)
        self.assertEqual(result['breakdown'][0]['avg_ms'], 200)

    def test_correction_factor_applied(self):
        """total_ms = raw_sum * 1.1, truncated to int."""
        graph = {'nodes': [{'type': 'click'}, {'type': 'click'}], 'edges': []}
        result = self.estimator.estimate(graph)
        raw = 2 * DEFAULT_NODE_DURATIONS['click']  # 400
        expected = int(raw * 1.1)  # 440
        self.assertEqual(result['total_ms'], expected)

    def test_unknown_node_type_defaults_to_5000(self):
        graph = {'nodes': [{'type': 'mystery_type'}], 'edges': []}
        result = self.estimator.estimate(graph)
        self.assertEqual(result['breakdown'][0]['avg_ms'], 5000)
        expected = int(1 * 5000 * 1.1)
        self.assertEqual(result['total_ms'], expected)

    def test_node_without_type_key(self):
        """Node missing 'type' key -> counted as 'unknown'."""
        graph = {'nodes': [{}], 'edges': []}
        result = self.estimator.estimate(graph)
        self.assertEqual(result['breakdown'][0]['node_type'], 'unknown')
        self.assertEqual(result['breakdown'][0]['avg_ms'], 5000)


class EstimateWaitNodesTests(TestCase):
    """wait nodes: item_total += max(0, timeout - 3000) per wait node."""

    def setUp(self):
        self.estimator = PipelineTimeEstimator()

    def test_wait_with_default_timeout(self):
        """No timeout in data -> defaults to 3000, no extra added."""
        graph = {'nodes': [{'type': 'wait'}], 'edges': []}
        result = self.estimator.estimate(graph)
        # base = 1 * 3000 = 3000; extra = max(0, 3000-3000) = 0
        expected_item = 3000
        self.assertEqual(result['breakdown'][0]['total_ms'], expected_item)
        self.assertEqual(result['total_ms'], int(3000 * 1.1))

    def test_wait_with_large_timeout(self):
        """timeout=5000 -> extra = 2000 per node."""
        graph = {
            'nodes': [{'type': 'wait', 'data': {'timeout': 5000}}],
            'edges': [],
        }
        result = self.estimator.estimate(graph)
        # base = 3000; extra = 2000; item_total = 5000
        self.assertEqual(result['breakdown'][0]['total_ms'], 5000)
        self.assertEqual(result['total_ms'], int(5000 * 1.1))

    def test_wait_with_small_timeout(self):
        """timeout=1000 -> extra = max(0, 1000-3000) = 0."""
        graph = {
            'nodes': [{'type': 'wait', 'data': {'timeout': 1000}}],
            'edges': [],
        }
        result = self.estimator.estimate(graph)
        self.assertEqual(result['breakdown'][0]['total_ms'], 3000)

    def test_multiple_wait_nodes(self):
        graph = {
            'nodes': [
                {'type': 'wait', 'data': {'timeout': 5000}},
                {'type': 'wait', 'data': {'timeout': 6000}},
            ],
            'edges': [],
        }
        result = self.estimator.estimate(graph)
        # base = 2 * 3000 = 6000; extra = 2000 + 3000 = 5000; item_total = 11000
        self.assertEqual(result['breakdown'][0]['count'], 2)
        self.assertEqual(result['breakdown'][0]['total_ms'], 11000)


class EstimateLoopNodesTests(TestCase):
    """loop nodes: item_total += (maxIterations - 1) * 2000 per loop node."""

    def setUp(self):
        self.estimator = PipelineTimeEstimator()

    def test_loop_default_iterations(self):
        """No maxIterations -> defaults to 1, extra = 0."""
        graph = {'nodes': [{'type': 'loop'}], 'edges': []}
        result = self.estimator.estimate(graph)
        # base = 1000; extra = (1-1)*2000 = 0
        self.assertEqual(result['breakdown'][0]['total_ms'], 1000)

    def test_loop_with_iterations(self):
        graph = {
            'nodes': [{'type': 'loop', 'data': {'maxIterations': 5}}],
            'edges': [],
        }
        result = self.estimator.estimate(graph)
        # base = 1000; extra = (5-1)*2000 = 8000; item_total = 9000
        self.assertEqual(result['breakdown'][0]['total_ms'], 9000)

    def test_multiple_loop_nodes(self):
        graph = {
            'nodes': [
                {'type': 'loop', 'data': {'maxIterations': 3}},
                {'type': 'loop', 'data': {'maxIterations': 2}},
            ],
            'edges': [],
        }
        result = self.estimator.estimate(graph)
        # base = 2 * 1000 = 2000; extra = (3-1)*2000 + (2-1)*2000 = 6000; total = 8000
        self.assertEqual(result['breakdown'][0]['count'], 2)
        self.assertEqual(result['breakdown'][0]['total_ms'], 8000)


class EstimateMixedNodesTests(TestCase):
    """Mixed node types in a single pipeline."""

    def setUp(self):
        self.estimator = PipelineTimeEstimator()

    def test_mixed_click_and_swipe(self):
        graph = {
            'nodes': [
                {'type': 'click'},
                {'type': 'swipe'},
                {'type': 'click'},
            ],
            'edges': [],
        }
        result = self.estimator.estimate(graph)
        # raw = (2*200) + (1*800) = 1200; total = int(1200 * 1.1) = 1320
        self.assertEqual(result['total_ms'], 1320)
        types = {b['node_type'] for b in result['breakdown']}
        self.assertEqual(types, {'click', 'swipe'})

    def test_breakdown_aggregation(self):
        """Multiple nodes of same type aggregate into one breakdown entry."""
        graph = {
            'nodes': [
                {'type': 'click'}, {'type': 'click'}, {'type': 'click'},
            ],
            'edges': [],
        }
        result = self.estimator.estimate(graph)
        self.assertEqual(len(result['breakdown']), 1)
        self.assertEqual(result['breakdown'][0]['count'], 3)
        self.assertEqual(result['breakdown'][0]['total_ms'], 3 * 200)


class EstimateReturnValueTests(TestCase):
    """Return value structure."""

    def setUp(self):
        self.estimator = PipelineTimeEstimator()

    def test_breakdown_entry_fields(self):
        graph = {'nodes': [{'type': 'click'}], 'edges': []}
        result = self.estimator.estimate(graph)
        entry = result['breakdown'][0]
        self.assertIn('node_type', entry)
        self.assertIn('count', entry)
        self.assertIn('avg_ms', entry)
        self.assertIn('total_ms', entry)

    def test_top_level_keys(self):
        result = self.estimator.estimate({'nodes': [], 'edges': []})
        self.assertIn('total_ms', result)
        self.assertIn('breakdown', result)

    def test_correction_factor_constant(self):
        self.assertEqual(PipelineTimeEstimator.CORRECTION_FACTOR, 1.1)
