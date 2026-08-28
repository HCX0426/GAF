"""TD-390: pipeline_guard.validate_and_score 单测 + generate_pipeline 响应含 validation。"""
import pytest

from gaf_ai.pipeline_guard import validate_and_score

pytestmark = pytest.mark.django_db


def _valid_pipeline():
    return {
        'nodes': [
            {'id': 's1', 'node_type': 'screenshot'},
            {'id': 's2', 'node_type': 'template_match'},
            {'id': 's3', 'node_type': 'click', 'x': 100, 'y': 200},
        ],
        'edges': [
            {'source': 's1', 'target': 's2'},
            {'source': 's2', 'target': 's3'},
        ],
    }


def test_valid_pipeline_passes():
    r = validate_and_score(_valid_pipeline())
    assert r['valid'] is True
    assert r['risk_level'] == 'medium'  # 一个 click (MEDIUM)
    assert r['cycle_detected'] is False
    assert r['high_risk_nodes'] == []


def test_cycle_detected_is_error():
    g = _valid_pipeline()
    g['edges'].append({'source': 's3', 'target': 's1'})  # 成环
    r = validate_and_score(g)
    assert r['valid'] is False
    assert r['cycle_detected'] is True
    assert any('循环' in e for e in r['errors'])


def test_out_of_range_coordinate_warns():
    g = _valid_pipeline()
    g['nodes'][2]['x'] = 99999
    r = validate_and_score(g)
    assert r['valid'] is True
    assert any('坐标' in w for w in r['warnings'])


def test_high_risk_node_flagged():
    g = {
        'nodes': [
            {'id': 'a', 'node_type': 'screenshot'},
            {'id': 'b', 'node_type': 'shell_command', 'cmd': 'rm -rf /'},
        ],
        'edges': [{'source': 'a', 'target': 'b'}],
    }
    r = validate_and_score(g)
    assert r['risk_level'] == 'high'
    assert r['high_risk_nodes'] == ['b']
    assert r['risk_score'] >= 3


def test_unreachable_isolated_node_warned():
    g = _valid_pipeline()
    g['nodes'].append({'id': 'orphan', 'node_type': 'click'})
    r = validate_and_score(g)
    assert 'orphan' in r['unreachable_nodes']
    assert any('不可达' in w for w in r['warnings'])


def test_missing_nodes_is_invalid():
    r = validate_and_score({'nodes': []})
    assert r['valid'] is False
    assert r['errors']


def test_non_dict_graph_is_invalid():
    r = validate_and_score('not a dict')
    assert r['valid'] is False
    assert r['risk_level'] == 'high'


def test_duplicate_node_id_error():
    g = _valid_pipeline()
    g['nodes'].append({'id': 's1', 'node_type': 'wait'})
    r = validate_and_score(g)
    assert any('重复' in e for e in r['errors'])
