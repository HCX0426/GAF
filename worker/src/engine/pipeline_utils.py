from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Hard upper bound for a single node execution. Individual nodes can override
# via config["timeout"] (spec 阶段 2.2). 5 minutes is generous enough for
# legitimate long-running nodes (wait/ocr on slow devices) while still
# catching genuine hangs.
MAX_STEP_TIMEOUT = 300.0


def _truncate_dict(data: Any, max_chars: int = 2000) -> Any:
    """N192 A6 P2: 截断 dict 的 str 表示到 max_chars, 超长则替换为 {_truncated: True, _keys: [...]}.

    防止大 dict (如完整 OCR 结果、大 detections 列表) 撑爆 JSONL 单行.
    """
    if data is None:
        return None
    try:
        s = json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        s = str(data)
    if len(s) <= max_chars:
        return data
    if isinstance(data, dict):
        return {"_truncated": True, "_keys": list(data.keys())[:20]}
    return {"_truncated": True, "_len": len(s)}


# N193 Task 5.2: previous_node_result_data 按字段重要性分级截断.
# 诊断关键字段 (confidence / match_loc / coord_system) 必须保留, 大对象
# (detections / boxes / texts) 替换为摘要, 让 AI 从 JSONL 就能定位失败
# 上下文, 不必跨多个事件拼凑.
# 字段优先级:
#   P0 必保 (诊断关键): confidence / threshold / match_loc / coord_system /
#       source / node_id / error_code / success — 不截断
#   P1 重要 (上下文): text / template_id / roi / bbox — 截断到 200 字符
#   P2 次要 (大对象): detections / boxes / texts / screenshot_path — 替换为
#       {"_truncated": True, "_count": N}
#   P3 其他: 统一截断到 500 字符
_RESULT_DATA_P0_FIELDS = frozenset({
    "confidence", "threshold", "match_loc", "match_location",
    "coord_system", "source", "node_id", "error_code", "success",
    # Task 4.11 (P2-11, 2026-07-28): feature_match / color_detect 关键诊断字段
    # 原本落到 P3 被截断到 500 字符, AI 无法从 previous_node_result_data
    # 看到匹配点数 / 内点数 / 是否命中, 无法反推"匹配点不足还是坐标转换错误".
    "num_matches", "inlier_matches", "matched",
})
_RESULT_DATA_P1_FIELDS = frozenset({
    "text", "template_id", "roi", "bbox", "match_bbox_phys",
})
_RESULT_DATA_P2_FIELDS = frozenset({
    "detections", "boxes", "texts", "screenshot_path", "raw_screenshot_path",
    "check_history", "auto_heal_attempts",
})


def _truncate_result_data_priority(data: Any, max_chars: int = 1000) -> Any:
    """N193 Task 5.2: 按字段重要性分级截断 result_data dict.

    保留 P0 诊断关键字段, 截断 P1 上下文字段, 替换 P2 大对象为摘要,
    P3 其他字段统一截断. 总长度仍超 max_chars 时 P3 → P2 → P1 依次降级,
    P0 始终保留.

    Args:
        data: 节点 result_data (dict 或其他). 非 dict 直接用 _truncate_dict.
        max_chars: 总长度上限. 默认 1000.

    Returns:
        截断后的 dict (或原值若不超长).
    """
    if data is None:
        return None
    if not isinstance(data, dict):
        return _truncate_dict(data, max_chars=max_chars)

    # 第一遍: 按优先级分类字段
    p0: dict[str, Any] = {}
    p1: dict[str, Any] = {}
    p2: dict[str, Any] = {}
    p3: dict[str, Any] = {}
    for k, v in data.items():
        if k in _RESULT_DATA_P0_FIELDS:
            p0[k] = v
        elif k in _RESULT_DATA_P1_FIELDS:
            p1[k] = v
        elif k in _RESULT_DATA_P2_FIELDS:
            p2[k] = v
        else:
            p3[k] = v

    # P2 大对象: 替换为摘要
    p2_truncated: dict[str, Any] = {}
    for k, v in p2.items():
        if isinstance(v, list):
            p2_truncated[k] = {"_truncated": True, "_count": len(v)}
        elif isinstance(v, str) and len(v) > 100:
            p2_truncated[k] = {"_truncated": True, "_len": len(v)}
        else:
            p2_truncated[k] = v

    # P1 上下文: 截断到 200 字符
    p1_truncated: dict[str, Any] = {}
    for k, v in p1.items():
        if isinstance(v, str) and len(v) > 200:
            p1_truncated[k] = v[:200] + "..._truncated"
        else:
            p1_truncated[k] = v

    # P3 其他: 截断到 500 字符
    p3_truncated: dict[str, Any] = {}
    for k, v in p3.items():
        if isinstance(v, str) and len(v) > 500:
            p3_truncated[k] = v[:500] + "..._truncated"
        else:
            p3_truncated[k] = v

    # 合并并检查总长度
    result = {**p0, **p1_truncated, **p2_truncated, **p3_truncated}
    try:
        s = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        s = str(result)

    if len(s) <= max_chars:
        return result

    # 总长度超限: P3 → P2 → P1 依次降级, P0 始终保留
    if p3_truncated:
        p3_truncated = {
            k: ({"_truncated": True, "_len": len(str(v))}
                if not isinstance(v, (int, float, bool)) and len(str(v)) > 50
                else v)
            for k, v in p3_truncated.items()
        }
        result = {**p0, **p1_truncated, **p2_truncated, **p3_truncated}
        try:
            s = json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            s = str(result)
        if len(s) <= max_chars:
            return result

    if p2_truncated:
        p2_truncated = {
            k: {"_truncated": True, "_omitted": True}
            for k in p2_truncated
        }
        result = {**p0, **p1_truncated, **p2_truncated, **p3_truncated}
        try:
            s = json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            s = str(result)
        if len(s) <= max_chars:
            return result

    if p1_truncated:
        p1_truncated = {
            k: (str(v)[:100] + "..._truncated" if isinstance(v, str) else v)
            for k, v in p1_truncated.items()
        }
        result = {**p0, **p1_truncated, **p2_truncated, **p3_truncated}

    return result
