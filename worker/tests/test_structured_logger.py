"""Tests for worker/src/utils/structured_logger.py — JSONL structured logging.

Verifies:
- JSONL format correctness (one JSON object per line)
- Thread-safety under concurrent log_node_event calls
- Optional fields are omitted when None (compact output)
- extract_result_fields() picks the right fields per node_type
- Best-effort semantics: write failures don't raise
- Per-execution file isolation (different execution_ids -> different files)
"""

from __future__ import annotations

import json
import threading

# Agent tests run with worker/src on sys.path (see pyproject.toml / conftest).
from utils.structured_logger import (
    extract_result_fields,
    get_logger,
    new_execution_id,
)


def _read_jsonl(path: str) -> list:
    """Read a JSONL file and return the list of parsed JSON objects."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ============================================================
# new_execution_id
# ============================================================

class TestNewExecutionId:
    def test_format_prefix(self):
        eid = new_execution_id()
        assert eid.startswith("exec-")
        assert len(eid) == len("exec-") + 12  # 12 hex chars

    def test_unique(self):
        ids = {new_execution_id() for _ in range(100)}
        assert len(ids) == 100


# ============================================================
# StructuredLogger basic
# ============================================================

class TestStructuredLoggerBasic:
    def test_creates_file_under_structured_dir(self, tmp_path):
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1",
            node_type="click",
            step_index=0,
            success=True,
            elapsed_ms=12.5,
        )
        expected = tmp_path / "structured" / f"{eid}.jsonl"
        assert expected.is_file()

    def test_writes_one_json_object_per_line(self, tmp_path):
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        log.log_node_event(
            event="node.execute.complete",
            node_id="n2", node_type="template_match",
            step_index=1, success=False, elapsed_ms=20,
            error_msg="threshold not met",
        )

        entries = _read_jsonl(str(tmp_path / "structured" / f"{eid}.jsonl"))
        assert len(entries) == 2
        assert entries[0]["node_id"] == "n1"
        assert entries[1]["node_id"] == "n2"
        assert entries[1]["error_msg"] == "threshold not met"

    def test_required_fields_present(self, tmp_path):
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10.0,
        )
        entries = _read_jsonl(str(tmp_path / "structured" / f"{eid}.jsonl"))
        e = entries[0]
        # Required fields per spec schema
        for key in (
            "timestamp", "execution_id", "node_id", "node_type",
            "step_index", "event", "success", "elapsed_ms",
            "retry_count", "error_msg",
        ):
            assert key in e, f"missing required field {key}"
        assert e["execution_id"] == eid
        assert e["timestamp"].endswith("Z")
        assert e["retry_count"] == 0

    def test_optional_fields_omitted_when_none(self, tmp_path):
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
            confidence=None, threshold=None,
            match_location=None, roi_base=None,
            screenshot_path=None, variables_snapshot=None,
            auto_heal_attempts=None,
        )
        entries = _read_jsonl(str(tmp_path / "structured" / f"{eid}.jsonl"))
        e = entries[0]
        # Optional fields must NOT be present when None
        for key in (
            "confidence", "threshold", "match_location",
            "roi_base", "screenshot_path",
            "variables_snapshot", "auto_heal_attempts",
        ):
            assert key not in e, f"optional field {key} should be omitted"

    def test_optional_fields_present_when_set(self, tmp_path):
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="template_match",
            step_index=0, success=True, elapsed_ms=10,
            confidence=0.95,
            threshold=0.8,
            match_location={"x": 100, "y": 200},
            roi_base=[10, 20, 30, 40],
            screenshot_path="debug/match_success_n1.png",
            variables_snapshot={"current_screen": "main"},
            auto_heal_attempts=["WGC", "DXGI"],
        )
        entries = _read_jsonl(str(tmp_path / "structured" / f"{eid}.jsonl"))
        e = entries[0]
        assert e["confidence"] == 0.95
        assert e["threshold"] == 0.8
        assert e["match_location"] == {"x": 100, "y": 200}
        assert e["roi_base"] == [10, 20, 30, 40]
        assert e["screenshot_path"] == "debug/match_success_n1.png"
        assert e["variables_snapshot"] == {"current_screen": "main"}
        assert e["auto_heal_attempts"] == ["WGC", "DXGI"]

    def test_extra_fields_merged(self, tmp_path):
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="ocr",
            step_index=0, success=True, elapsed_ms=10,
            extra={"recognized_text": "hello", "ocr_engine": "paddle"},
        )
        entries = _read_jsonl(str(tmp_path / "structured" / f"{eid}.jsonl"))
        e = entries[0]
        assert e["recognized_text"] == "hello"
        assert e["ocr_engine"] == "paddle"

    def test_error_code_omitted_when_empty(self, tmp_path):
        """成功节点 error_code 默认空字符串，JSONL 中应省略该字段。"""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        entries = _read_jsonl(str(tmp_path / "structured" / f"{eid}.jsonl"))
        assert "error_code" not in entries[0]

    def test_error_code_written_when_provided(self, tmp_path):
        """失败节点传入 error_code 时应写入 JSONL。"""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="step_3", node_type="template_match",
            step_index=2, success=False, elapsed_ms=1500.0,
            error_msg="模板匹配失败",
            error_code="NO_MATCH",
        )
        entries = _read_jsonl(str(tmp_path / "structured" / f"{eid}.jsonl"))
        e = entries[0]
        assert e["success"] is False
        assert e["error_msg"] == "模板匹配失败"
        assert e["error_code"] == "NO_MATCH"

    def test_error_code_accepts_node_error_code_enum(self, tmp_path):
        """error_code 应接受 NodeErrorCode 枚举值（StrEnum 自动转 str）。"""
        from gaf_core.error_codes import NodeErrorCode

        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="step_1", node_type="click",
            step_index=0, success=False, elapsed_ms=200.0,
            error_msg="点击后画面未变化",
            error_code=NodeErrorCode.SCREEN_UNCHANGED,
        )
        entries = _read_jsonl(str(tmp_path / "structured" / f"{eid}.jsonl"))
        # StrEnum 子类实例在 json.dumps 中应输出为字符串值
        assert entries[0]["error_code"] == "SCREEN_UNCHANGED"

    def test_raw_screenshot_path_omitted_when_none(self, tmp_path):
        """raw_screenshot_path 为 None 时应从 JSONL 省略（动作类节点）。"""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
            screenshot_path="/tmp/annotated.png",
            # raw_screenshot_path 不传 → 默认 None → 省略
        )
        entries = _read_jsonl(str(tmp_path / "structured" / f"{eid}.jsonl"))
        e = entries[0]
        assert e["screenshot_path"] == "/tmp/annotated.png"
        assert "raw_screenshot_path" not in e

    def test_raw_screenshot_path_written_when_provided(self, tmp_path):
        """raw_screenshot_path 有值时应写入 JSONL（识别类节点）。"""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="step_3", node_type="template_match",
            step_index=2, success=True, elapsed_ms=120.0,
            screenshot_path="/tmp/screenshots/annotated/match_success_btn_143025.png",
            raw_screenshot_path="/tmp/screenshots/raw/match_success_btn_143025.jpg",
        )
        entries = _read_jsonl(str(tmp_path / "structured" / f"{eid}.jsonl"))
        e = entries[0]
        assert e["screenshot_path"].endswith("match_success_btn_143025.png")
        assert e["raw_screenshot_path"].endswith("match_success_btn_143025.jpg")


# ============================================================
# Thread safety
# ============================================================

class TestStructuredLoggerConcurrency:
    def test_concurrent_writes_do_not_corrupt_lines(self, tmp_path):
        """N threads each writing M lines -> all lines must parse as JSON."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        n_threads = 8
        m_lines = 50

        def writer(thread_idx: int) -> None:
            for i in range(m_lines):
                log.log_node_event(
                    event="node.execute.complete",
                    node_id=f"t{thread_idx}_n{i}",
                    node_type="click",
                    step_index=i,
                    success=True,
                    elapsed_ms=float(i),
                )

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        path = str(tmp_path / "structured" / f"{eid}.jsonl")
        entries = _read_jsonl(path)
        # Every line must parse as JSON (already asserted by _read_jsonl).
        assert len(entries) == n_threads * m_lines
        # Every entry has required fields
        for e in entries:
            assert "node_id" in e
            assert "execution_id" in e
            assert e["execution_id"] == eid

    def test_same_execution_id_shares_one_file(self, tmp_path):
        """get_logger(eid, dir) returns the same instance for same eid+dir."""
        eid = new_execution_id()
        log1 = get_logger(eid, debug_dir=str(tmp_path))
        log2 = get_logger(eid, debug_dir=str(tmp_path))
        assert log1 is log2
        assert log1.file_path == log2.file_path

    def test_different_execution_ids_get_different_files(self, tmp_path):
        eid1 = new_execution_id()
        eid2 = new_execution_id()
        log1 = get_logger(eid1, debug_dir=str(tmp_path))
        log2 = get_logger(eid2, debug_dir=str(tmp_path))
        assert log1.file_path != log2.file_path


# ============================================================
# Best-effort semantics
# ============================================================

class TestStructuredLoggerBestEffort:
    def test_close_blocks_future_writes(self, tmp_path):
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        log.close()
        # After close, log_node_event should be a no-op
        log.log_node_event(
            event="node.execute.complete",
            node_id="n2", node_type="click",
            step_index=1, success=True, elapsed_ms=10,
        )
        path = str(tmp_path / "structured" / f"{eid}.jsonl")
        entries = _read_jsonl(path)
        # Only the pre-close line should be present
        assert len(entries) == 1
        assert entries[0]["node_id"] == "n1"


# ============================================================
# extract_result_fields
# ============================================================

class TestExtractResultFields:
    def test_template_match_extracts_all_fields(self):
        data = {
            "confidence": 0.95,
            "x": 100,
            "y": 200,
            "match_loc": {"x": 50, "y": 60},
            "screenshot_path": "debug/match.png",
            "auto_heal_method": "WGC",
        }
        config = {"threshold": 0.8, "roi": [10, 20, 30, 40]}
        out = extract_result_fields("template_match", data, config)
        assert out["confidence"] == 0.95
        assert out["threshold"] == 0.8
        assert out["match_location"] == {"x": 50, "y": 60}  # match_loc wins
        assert out["roi_base"] == [10, 20, 30, 40]
        assert out["screenshot_path"] == "debug/match.png"
        assert out["auto_heal_attempts"] == ["WGC"]

    def test_template_match_falls_back_to_xy_when_no_match_loc(self):
        data = {"confidence": 0.95, "x": 100, "y": 200}
        config = {"threshold": 0.8}
        out = extract_result_fields("template_match", data, config)
        assert out["match_location"] == {"x": 100, "y": 200}

    def test_click_extracts_only_screenshot_path(self):
        data = {"x": 100, "y": 200, "screenshot_path": "debug/click.png"}
        config = {}
        out = extract_result_fields("click", data, config)
        # click nodes have no confidence/threshold/roi
        assert "confidence" not in out
        assert "threshold" not in out
        assert "roi_base" not in out
        assert out["screenshot_path"] == "debug/click.png"

    def test_non_dict_result_returns_empty(self):
        out = extract_result_fields("template_match", None, {})
        assert out == {}
        out = extract_result_fields("template_match", "string_result", {})
        assert out == {}

    def test_empty_screenshot_path_omitted(self):
        data = {"screenshot_path": ""}
        out = extract_result_fields("click", data, {})
        assert "screenshot_path" not in out


# ============================================================
# extract_result_fields — 新增节点分支 (spec 阶段 3.1 — 任务 1.3)
# ============================================================

class TestExtractResultFieldsClickBranch:
    """click 分支：提取坐标、点击参数、竞态防护结果字段。"""

    def test_click_extracts_match_location_from_xy(self):
        data = {"x": 960, "y": 540}
        out = extract_result_fields("click", data, {})
        assert out["match_location"] == {"x": 960, "y": 540}

    def test_click_extracts_click_input_when_present(self):
        """点击坐标可能与输出坐标不同（经过坐标变换），需独立保留。"""
        data = {"x": 960, "y": 540, "x_in": 100, "y_in": 200}
        out = extract_result_fields("click", data, {})
        assert out["match_location"] == {"x": 960, "y": 540}
        assert out["click_input"] == {"x": 100, "y": 200}

    def test_click_extracts_optional_click_params(self):
        """button/clicks/interval/coord_type/normalization_applied 应原样保留。"""
        data = {
            "x": 100, "y": 200,
            "button": "right",
            "clicks": 2,
            "interval": 0.1,
            "coord_type": "normalized",
            "normalization_applied": True,
        }
        out = extract_result_fields("click", data, {})
        assert out["button"] == "right"
        assert out["clicks"] == 2
        assert out["interval"] == 0.1
        assert out["coord_type"] == "normalized"
        assert out["normalization_applied"] is True

    def test_click_omits_optional_params_when_absent(self):
        """未提供的可选字段不应出现在输出中。"""
        data = {"x": 100, "y": 200}
        out = extract_result_fields("click", data, {})
        assert "button" not in out
        assert "click_input" not in out

    def test_click_extracts_race_protection_fields(self):
        """竞态防护结果（spec 阶段 4.2）应进 JSONL 便于 AI 诊断。"""
        data = {
            "x": 100, "y": 200,
            "expect_screen_change": True,
            "screen_change_outcome": "CHANGED",
        }
        out = extract_result_fields("click", data, {})
        assert out["expect_screen_change"] is True
        assert out["screen_change_outcome"] == "CHANGED"

    def test_click_without_coordinates_returns_only_common_fields(self):
        """无坐标的 click 结果（罕见但需兼容）只返回公共字段。"""
        data = {"screenshot_path": "debug/click.png"}
        out = extract_result_fields("click", data, {})
        assert "match_location" not in out
        assert out["screenshot_path"] == "debug/click.png"


class TestExtractResultFieldsOcrBranch:
    """ocr 分支：提取识别文本、置信度、box、期望文本。"""

    def test_ocr_extracts_first_10_texts_truncated(self):
        texts = [f"text_{i}" for i in range(15)]
        data = {"texts": texts, "text_count": 15}
        out = extract_result_fields("ocr", data, {})
        assert len(out["texts"]) == 10
        assert out["texts"] == [f"text_{i}" for i in range(10)]
        assert out["text_count"] == 15

    def test_ocr_truncates_long_text_to_200_chars(self):
        long_text = "x" * 300
        data = {"texts": [long_text]}
        out = extract_result_fields("ocr", data, {})
        assert len(out["texts"][0]) == 200

    def test_ocr_extracts_confidences_and_boxes_top10(self):
        data = {
            "texts": ["a", "b", "c"],
            "confidences": [0.95, 0.88, 0.72],
            "boxes": [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]],
        }
        out = extract_result_fields("ocr", data, {})
        assert out["confidences_top10"] == [0.95, 0.88, 0.72]
        assert out["boxes_top10"] == [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]

    def test_ocr_extracts_expected_text_for_failure_diagnosis(self):
        data = {"texts": [], "expected_text": "确定"}
        out = extract_result_fields("ocr", data, {})
        assert out["expected_text"] == "确定"

    def test_ocr_with_empty_texts_omits_text_fields(self):
        data = {"texts": []}
        out = extract_result_fields("ocr", data, {})
        assert "texts" not in out
        assert "text_count" not in out


class TestExtractResultFieldsWaitBranch:
    """wait 分支：提取 mode/max_wait + check_history 最近 3 条。"""

    def test_wait_extracts_mode_and_max_wait(self):
        data = {"mode": "fixed", "max_wait": 10.0}
        out = extract_result_fields("wait", data, {})
        assert out["mode"] == "fixed"
        assert out["max_wait"] == 10.0

    def test_wait_extracts_last_3_check_history_entries(self):
        history = [
            {"check_index": i, "elapsed_s": 0.5 * i, "confidence": 0.1 * i, "screenshot": f"s{i}.png"}
            for i in range(5)
        ]
        data = {"check_history": history}
        out = extract_result_fields("wait", data, {})
        assert len(out["check_history"]) == 3
        # 应保留最后 3 条 (index 2,3,4)
        assert out["check_history"][0]["check_index"] == 2
        assert out["check_history"][-1]["check_index"] == 4
        # 字段精简：保留 check_index/elapsed_s/confidence/screenshot
        assert "elapsed_s" in out["check_history"][0]
        assert "confidence" in out["check_history"][0]

    def test_wait_with_no_check_history_omits_field(self):
        data = {"mode": "fixed"}
        out = extract_result_fields("wait", data, {})
        assert "check_history" not in out


class TestExtractResultFieldsSwipeUntilBranch:
    """swipe_until 分支：提取 attempts/swipes_performed。"""

    def test_swipe_until_extracts_attempts_and_swipes_performed(self):
        data = {"attempts": 5, "swipes_performed": 4}
        out = extract_result_fields("swipe_until", data, {})
        assert out["attempts"] == 5
        assert out["swipes_performed"] == 4

    def test_swipe_until_with_only_one_field(self):
        data = {"attempts": 3}
        out = extract_result_fields("swipe_until", data, {})
        assert out["attempts"] == 3
        assert "swipes_performed" not in out


# ============================================================
# N192 A6 P3: 字符串字段截断保护
# ============================================================

class TestStringFieldTruncation:
    """log_node_event 的字符串字段 (error_msg / comment / rationale) 应被
    截断到 MAX_STR_FIELD_LEN, 防止大堆栈撑爆 JSONL 单行.

    覆盖 N192 A6 P3: 截断保护.
    """

    def test_long_error_msg_is_truncated(self, tmp_path):
        """error_msg 超 2000 字符应被截断, 含 _truncated 标记."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        long_msg = "x" * 5000
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1",
            node_type="template_match",
            step_index=0,
            success=False,
            elapsed_ms=100,
            error_msg=long_msg,
        )
        log.close()
        events = _read_jsonl(log.file_path)
        assert len(events) == 1
        evt = events[0]
        truncated = evt["error_msg"]
        # 截断后长度应远小于 5000
        assert len(truncated) < 5000
        # 应含 _truncated 标记和原始长度
        assert "_truncated" in truncated
        assert "original_len=5000" in truncated

    def test_short_error_msg_not_truncated(self, tmp_path):
        """短 error_msg 不应被截断."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1",
            node_type="click",
            step_index=0,
            success=False,
            elapsed_ms=50,
            error_msg="点击失败: 元素未找到",
        )
        log.close()
        events = _read_jsonl(log.file_path)
        assert events[0]["error_msg"] == "点击失败: 元素未找到"

    def test_long_comment_is_truncated(self, tmp_path):
        """comment 字段超长也应被截断."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        long_comment = "这是节点注释 " * 500  # 约 4000 字符
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1",
            node_type="click",
            step_index=0,
            success=True,
            elapsed_ms=50,
            comment=long_comment,
        )
        log.close()
        events = _read_jsonl(log.file_path)
        comment = events[0]["comment"]
        assert "_truncated" in comment
        assert "original_len=" in comment

    def test_long_rationale_is_truncated(self, tmp_path):
        """rationale 字段超长也应被截断."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        long_rationale = "因为..." * 1000  # 约 4000 字符
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1",
            node_type="click",
            step_index=0,
            success=True,
            elapsed_ms=50,
            rationale=long_rationale,
        )
        log.close()
        events = _read_jsonl(log.file_path)
        rationale = events[0]["rationale"]
        assert "_truncated" in rationale

    def test_truncation_preserves_prefix(self, tmp_path):
        """截断后前缀应保留 (让 AI 能看到错误的开头部分)."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        # 构造一个有意义的开头 + 超长尾部
        msg = "KeyError: 'steps' in pipeline config. " + "x" * 5000
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1",
            node_type="template_match",
            step_index=0,
            success=False,
            elapsed_ms=50,
            error_msg=msg,
        )
        log.close()
        events = _read_jsonl(log.file_path)
        truncated = events[0]["error_msg"]
        # 前缀 "KeyError: 'steps'..." 应保留
        assert truncated.startswith("KeyError: 'steps'")

    def test_orchestrator_error_msg_also_truncated(self, tmp_path):
        """log_orchestrator_event 的 error_msg 也应被截断 (与 node 级一致)."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        long_msg = "y" * 5000
        log.log_orchestrator_event(
            event="orchestrator.task.failed",
            task_state="failed",
            success=False,
            error_msg=long_msg,
        )
        log.close()
        events = _read_jsonl(log.file_path)
        assert len(events) == 1
        truncated = events[0]["error_msg"]
        assert len(truncated) < 5000
        assert "_truncated" in truncated
        assert "original_len=5000" in truncated


class TestNodeExecuteStartEventOmitsSuccessField:
    """N193 Task 5.1: node.execute.start 事件省略 success / error_msg /
    error_code 字段.

    start 事件语义是"节点开始执行", 尚无成功/失败概念. 写 success=True
    会让 AI 误判为"成功完成", 写 success=False 会让 AI 误判为"已失败".
    这些字段是 complete 事件专属.
    """

    def test_start_event_omits_success_field(self, tmp_path):
        """start 事件的 payload 不应含 success 字段."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.start",
            node_id="n1",
            node_type="click",
            step_index=0,
            success=True,  # 调用方传 True 作占位, logger 应忽略
            elapsed_ms=0,
        )
        log.close()
        events = _read_jsonl(log.file_path)
        assert len(events) == 1
        evt = events[0]
        assert "success" not in evt, (
            f"start 事件不应含 success 字段, 实际: {list(evt.keys())}"
        )

    def test_start_event_omits_error_msg_field(self, tmp_path):
        """start 事件的 payload 不应含 error_msg 字段."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.start",
            node_id="n1",
            node_type="click",
            step_index=0,
            success=True,
            elapsed_ms=0,
            error_msg="不应出现",  # 调用方误传, logger 应忽略
        )
        log.close()
        events = _read_jsonl(log.file_path)
        evt = events[0]
        assert "error_msg" not in evt, (
            f"start 事件不应含 error_msg 字段, 实际: {list(evt.keys())}"
        )

    def test_start_event_omits_error_code_field(self, tmp_path):
        """start 事件的 payload 不应含 error_code 字段."""
        from core.error_codes import NodeErrorCode

        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.start",
            node_id="n1",
            node_type="template_match",
            step_index=0,
            success=True,
            elapsed_ms=0,
            error_code=NodeErrorCode.NO_MATCH,  # 调用方误传, logger 应忽略
        )
        log.close()
        events = _read_jsonl(log.file_path)
        evt = events[0]
        assert "error_code" not in evt, (
            f"start 事件不应含 error_code 字段, 实际: {list(evt.keys())}"
        )

    def test_complete_event_still_has_success_field(self, tmp_path):
        """complete 事件应正常保留 success / error_msg / error_code 字段."""
        from core.error_codes import NodeErrorCode

        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1",
            node_type="template_match",
            step_index=0,
            success=False,
            elapsed_ms=100,
            error_msg="模板未匹配",
            error_code=NodeErrorCode.NO_MATCH,
        )
        log.close()
        events = _read_jsonl(log.file_path)
        evt = events[0]
        assert evt["success"] is False
        assert evt["error_msg"] == "模板未匹配"
        assert evt["error_code"] == "NO_MATCH"


# ============================================================
# A1 (spec 2026-07-30-debug-directory-restructure): 新路径结构
# debug/YYYYMMDD/agent/<pipeline>/HH/structured.jsonl
# ============================================================

class TestA1NewHourBucketPath:
    """A1: pipeline_name + trace_id 触发新结构路径 (小时桶).

    旧路径 ``<debug_dir>/structured/<execution_id>.jsonl`` 在 pipeline_name
    和 trace_id 都为空时仍走 (兼容 CLI 模式 / 现有测试).
    """

    def test_pipeline_name_triggers_new_path(self, tmp_path):
        """pipeline_name 非空时, 文件应写到 <debug_dir>/<YYYYMMDD>/agent/<pipeline>/HH/."""
        from utils.structured_logger import _now_local, get_logger
        eid = new_execution_id()
        log = get_logger(
            eid, debug_dir=str(tmp_path),
            pipeline_name="get_email", trace_id="trace-001",
        )
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        log.close()

        now = _now_local()
        date_part = now.strftime("%Y%m%d")
        hour_part = now.strftime("%H")
        expected = tmp_path / date_part / "agent" / "get_email" / hour_part / "structured.jsonl"
        assert expected.is_file(), f"文件应写到 {expected}, 实际 file_path={log.file_path}"

    def test_trace_id_only_triggers_new_path(self, tmp_path):
        """trace_id 非空 (pipeline_name 空) 也走新路径, pipeline 段用 unknown 兜底."""
        from utils.structured_logger import _now_local, get_logger
        eid = new_execution_id()
        log = get_logger(
            eid, debug_dir=str(tmp_path),
            pipeline_name="", trace_id="trace-002",
        )
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        log.close()

        now = _now_local()
        date_part = now.strftime("%Y%m%d")
        hour_part = now.strftime("%H")
        expected = tmp_path / date_part / "agent" / "unknown" / hour_part / "structured.jsonl"
        assert expected.is_file(), f"pipeline_name 空应用 unknown 兜底, 期望 {expected}"

    def test_both_empty_uses_legacy_path(self, tmp_path):
        """pipeline_name 和 trace_id 都空时走 legacy 路径 (向后兼容)."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        log.close()
        # Legacy: <debug_dir>/structured/<execution_id>.jsonl
        expected = tmp_path / "structured" / f"{eid}.jsonl"
        assert expected.is_file()

    def test_pipeline_name_sanitized_in_path(self, tmp_path):
        """pipeline_name 含特殊字符时应被 sanitize (替换为 _)."""
        from utils.structured_logger import _now_local, get_logger
        eid = new_execution_id()
        log = get_logger(
            eid, debug_dir=str(tmp_path),
            pipeline_name="get email/test", trace_id="t1",
        )
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        log.close()

        now = _now_local()
        date_part = now.strftime("%Y%m%d")
        hour_part = now.strftime("%H")
        # "get email/test" → "get_email_test"
        expected = tmp_path / date_part / "agent" / "get_email_test" / hour_part / "structured.jsonl"
        assert expected.is_file(), f"特殊字符应被 sanitize, 期望 {expected}"


class TestA1TraceIdInjection:
    """A1: payload 注入 trace_id 和 pipeline_name 字段 (非空时)."""

    def test_trace_id_injected_into_payload(self, tmp_path):
        """log_node_event 写入的 JSONL 行应含 trace_id 字段."""
        eid = new_execution_id()
        log = get_logger(
            eid, debug_dir=str(tmp_path),
            pipeline_name="p1", trace_id="550e8400-e29b-41d4-a716-446655440000",
        )
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        log.close()
        entries = _read_jsonl(log.file_path)
        assert entries[0]["trace_id"] == "550e8400-e29b-41d4-a716-446655440000"

    def test_pipeline_name_injected_into_payload(self, tmp_path):
        """log_node_event 写入的 JSONL 行应含 pipeline_name 字段."""
        eid = new_execution_id()
        log = get_logger(
            eid, debug_dir=str(tmp_path),
            pipeline_name="get_email", trace_id="t1",
        )
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        log.close()
        entries = _read_jsonl(log.file_path)
        assert entries[0]["pipeline_name"] == "get_email"

    def test_trace_id_omitted_when_empty(self, tmp_path):
        """trace_id 为空时, JSONL 行不应含 trace_id 字段 (legacy 模式)."""
        eid = new_execution_id()
        log = get_logger(eid, debug_dir=str(tmp_path))
        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        log.close()
        entries = _read_jsonl(log.file_path)
        assert "trace_id" not in entries[0]
        assert "pipeline_name" not in entries[0]

    def test_orchestrator_event_injects_trace_id(self, tmp_path):
        """log_orchestrator_event 写入的 JSONL 行也应含 trace_id 字段."""
        eid = new_execution_id()
        log = get_logger(
            eid, debug_dir=str(tmp_path),
            pipeline_name="p1", trace_id="trace-orch-001",
        )
        log.log_orchestrator_event(
            event="orchestrator.task.start",
            task_state="running",
        )
        log.close()
        entries = _read_jsonl(log.file_path)
        assert entries[0]["trace_id"] == "trace-orch-001"


class TestA1HourRotation:
    """A1: 小时切换时, 后续事件写到新小时桶的文件.

    用 monkeypatch 模拟时间变化, 验证 _maybe_rotate_for_hour 切换路径.
    """

    def test_hour_change_rotates_file(self, tmp_path, monkeypatch):
        """小时变化后, 后续 log_node_event 写到新文件."""
        from utils import structured_logger as sl_module

        # 第一次写入 (current hour)
        eid = new_execution_id()
        log = sl_module.get_logger(
            eid, debug_dir=str(tmp_path),
            pipeline_name="p1", trace_id="t1",
        )
        # get_logger 已自动设置 _debug_dir_root (A1 fix), 无需手动赋值

        # 模拟时间: 第一次写入在 10 点
        import datetime as dt
        base_time = dt.datetime(2026, 7, 30, 10, 30, 0)
        monkeypatch.setattr(sl_module, "_now_local", lambda: base_time)

        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )

        # 模拟时间: 第二次写入在 11 点 (小时切换)
        new_time = dt.datetime(2026, 7, 30, 11, 5, 0)
        monkeypatch.setattr(sl_module, "_now_local", lambda: new_time)

        log.log_node_event(
            event="node.execute.complete",
            node_id="n2", node_type="click",
            step_index=1, success=True, elapsed_ms=20,
        )
        log.close()

        # 旧小时桶 (10) 应有 n1
        old_file = tmp_path / "20260730" / "agent" / "p1" / "10" / "structured.jsonl"
        # 新小时桶 (11) 应有 n2
        new_file = tmp_path / "20260730" / "agent" / "p1" / "11" / "structured.jsonl"

        assert old_file.is_file(), f"旧小时桶文件应存在: {old_file}"
        assert new_file.is_file(), f"新小时桶文件应存在: {new_file}"

        old_entries = _read_jsonl(str(old_file))
        new_entries = _read_jsonl(str(new_file))
        assert len(old_entries) == 1
        assert old_entries[0]["node_id"] == "n1"
        assert len(new_entries) == 1
        assert new_entries[0]["node_id"] == "n2"

    def test_no_rotation_when_hour_unchanged(self, tmp_path, monkeypatch):
        """小时未变化时, 所有事件写到同一文件."""
        import datetime as dt

        from utils import structured_logger as sl_module

        fixed_time = dt.datetime(2026, 7, 30, 10, 30, 0)
        monkeypatch.setattr(sl_module, "_now_local", lambda: fixed_time)

        eid = new_execution_id()
        log = sl_module.get_logger(
            eid, debug_dir=str(tmp_path),
            pipeline_name="p2", trace_id="t2",
        )
        # get_logger 已自动设置 _debug_dir_root (A1 fix), 无需手动赋值

        log.log_node_event(
            event="node.execute.complete",
            node_id="n1", node_type="click",
            step_index=0, success=True, elapsed_ms=10,
        )
        log.log_node_event(
            event="node.execute.complete",
            node_id="n2", node_type="click",
            step_index=1, success=True, elapsed_ms=20,
        )
        log.close()

        # 同一小时桶
        same_file = tmp_path / "20260730" / "agent" / "p2" / "10" / "structured.jsonl"
        assert same_file.is_file()
        entries = _read_jsonl(str(same_file))
        assert len(entries) == 2
        assert entries[0]["node_id"] == "n1"
        assert entries[1]["node_id"] == "n2"
