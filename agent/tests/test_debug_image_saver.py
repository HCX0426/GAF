"""DebugImageSaver 截图双保留测试 (spec 阶段 6 — 任务 2.1)

验证识别类节点（template_match / ocr / feature_match / color_detect）
生成 raw/ + annotated/ 两张图，文件名一致（仅扩展名不同）；动作类
节点（click / swipe / key_press / wait）只生成 annotated/。

设计原则（spec §6.2）：
- 识别类需原图：OCR 漏识别 / 模板错位 / 颜色判断失败都要 AI 看真实画面
- 动作类不需要原图：标注图（红叉 + 坐标 / 箭头）已包含全部诊断信息
- 原图 JPEG q=85（200-400KB），标注图 PNG 无损
- 同文件名靠目录区分用途，便于 AI/用户对照
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

_AGENT_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(_AGENT_SRC))

from utils.debug_image_saver import DebugImageSaver  # noqa: E402 - after sys.path setup above

pytestmark = pytest.mark.unit


def _make_screen(width: int = 200, height: int = 100) -> np.ndarray:
    """Build a BGR screenshot with detectable content."""
    screen = np.zeros((height, width, 3), dtype=np.uint8)
    screen[:, :, 1] = 128  # green channel
    return screen


def _make_template(size: int = 30) -> np.ndarray:
    """Build a small BGR template image."""
    tpl = np.zeros((size, size, 3), dtype=np.uint8)
    tpl[:, :, 2] = 255  # red
    return tpl


# ============================================================
# 原图保留策略 (spec §6.2)
# ============================================================

class TestRawImageRetentionPolicy:
    """识别类节点保留原图；动作类节点不保留。"""

    def test_template_match_creates_both_raw_and_annotated(self, tmp_path):
        """template_match 应同时生成 raw + annotated。"""
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()
        template = _make_template()

        paths = saver.save_template_debug(
            screen=screen,
            template_orig=template,
            template_scaled=template,
            template_name="login_btn",
            is_success=True,
            confidence=0.95,
            threshold=0.8,
            scale_ratio=1.0,
        )

        assert paths["annotated"] is not None
        assert paths["raw"] is not None
        raw_dir = tmp_path / "screenshots" / "raw"
        ann_dir = tmp_path / "screenshots" / "annotated"
        assert raw_dir.is_dir()
        assert ann_dir.is_dir()

        raw_files = list(raw_dir.glob("*.jpg"))
        ann_files = list(ann_dir.glob("*.png"))
        assert len(raw_files) == 1
        assert len(ann_files) == 1
        # 文件名一致（仅扩展名不同）
        assert raw_files[0].stem == ann_files[0].stem
        # 返回的 paths 与文件系统一致
        assert paths["raw"] == str(raw_files[0])
        assert paths["annotated"] == str(ann_files[0])

    def test_ocr_creates_both_raw_and_annotated(self, tmp_path):
        """OCR 应同时生成 raw + annotated。"""
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()

        paths = saver.save_ocr_debug(
            screen=screen,
            node_id="step_3",
            is_success=True,
            texts=["hello"],
            confidences=[0.9],
            boxes=[[10, 10, 50, 30]],
        )

        assert paths["annotated"] is not None
        assert paths["raw"] is not None
        raw_dir = tmp_path / "screenshots" / "raw"
        ann_dir = tmp_path / "screenshots" / "annotated"
        assert raw_dir.is_dir()
        assert ann_dir.is_dir()

        raw_files = list(raw_dir.glob("*.jpg"))
        ann_files = list(ann_dir.glob("*.png"))
        assert len(raw_files) == 1
        assert len(ann_files) == 1
        assert raw_files[0].stem == ann_files[0].stem

    def test_click_does_not_create_raw(self, tmp_path):
        """click 节点不应生成原图（标注图已够诊断）。"""
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()

        paths = saver.save_action_debug(
            screen=screen,
            node_id="step_5",
            node_type="click",
            is_success=True,
            action_info={"x": 100, "y": 50},
        )

        # 动作类节点 raw 应为 None
        assert paths["raw"] is None
        assert paths["annotated"] is not None
        raw_dir = tmp_path / "screenshots" / "raw"
        # raw 目录不应存在（_should_save_raw=False 时不创建）
        assert not raw_dir.exists() or not list(raw_dir.glob("*"))

    def test_swipe_does_not_create_raw(self, tmp_path):
        """swipe 节点不应生成原图。"""
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()

        paths = saver.save_action_debug(
            screen=screen,
            node_id="step_6",
            node_type="swipe",
            is_success=True,
            action_info={"start": [10, 50], "end": [100, 50]},
        )

        assert paths["raw"] is None
        assert paths["annotated"] is not None
        raw_dir = tmp_path / "screenshots" / "raw"
        assert not raw_dir.exists() or not list(raw_dir.glob("*"))


# ============================================================
# 原图格式与质量 (spec §6.3)
# ============================================================

class TestRawImageFormat:
    """原图应为 JPEG q=85 格式。"""

    def test_raw_image_is_jpeg(self, tmp_path):
        """raw/ 下的文件应为 .jpg 扩展名且可被 cv2 读取为 JPEG。"""
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()
        template = _make_template()

        saver.save_template_debug(
            screen=screen,
            template_orig=template,
            template_scaled=template,
            template_name="btn",
            is_success=True,
            confidence=0.9,
            threshold=0.8,
            scale_ratio=1.0,
        )

        raw_files = list((tmp_path / "screenshots" / "raw").glob("*"))
        assert raw_files[0].suffix == ".jpg"
        # cv2 应能读取
        img = cv2.imread(str(raw_files[0]))
        assert img is not None
        assert img.shape[0] == screen.shape[0]
        assert img.shape[1] == screen.shape[1]

    def test_annotated_image_is_png(self, tmp_path):
        """annotated/ 下的文件应为 .png 扩展名（无损）。"""
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()

        saver.save_ocr_debug(
            screen=screen,
            node_id="s1",
            is_success=True,
            texts=["t"],
            confidences=[0.9],
            boxes=[[1, 2, 3, 4]],
        )

        ann_files = list((tmp_path / "screenshots" / "annotated").glob("*"))
        assert ann_files[0].suffix == ".png"


# ============================================================
# 返回值结构 (spec §6.4)
# ============================================================

class TestReturnValuesAndBackwardCompat:
    """save_*_debug 返回 dict {annotated, raw}。"""

    def test_save_template_debug_returns_annotated_path(self, tmp_path):
        """save_template_debug 返回的 annotated 应是 annotated/ 下的 PNG。"""
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()
        template = _make_template()

        paths = saver.save_template_debug(
            screen=screen,
            template_orig=template,
            template_scaled=template,
            template_name="t1",
            is_success=False,
            confidence=0.3,
            threshold=0.8,
            scale_ratio=1.0,
        )

        assert paths["annotated"] is not None
        assert "annotated" in paths["annotated"].replace("\\", "/")
        assert paths["annotated"].endswith(".png")
        # 识别类节点应有 raw 路径
        assert paths["raw"] is not None
        assert "raw" in paths["raw"].replace("\\", "/")
        assert paths["raw"].endswith(".jpg")

    def test_save_ocr_debug_returns_annotated_path(self, tmp_path):
        """save_ocr_debug 返回的 annotated 应是 annotated/ 下的 PNG。"""
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()

        paths = saver.save_ocr_debug(
            screen=screen,
            node_id="ocr_step",
            is_success=False,
            texts=[],
            confidences=[],
            boxes=[],
        )

        assert paths["annotated"] is not None
        assert "annotated" in paths["annotated"].replace("\\", "/")
        assert paths["annotated"].endswith(".png")
        # OCR 属识别类，应有 raw
        assert paths["raw"] is not None

    def test_save_action_debug_returns_annotated_path(self, tmp_path):
        """save_action_debug 返回的 annotated 应是 annotated/ 下的 PNG。"""
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()

        paths = saver.save_action_debug(
            screen=screen,
            node_id="click_step",
            node_type="click",
            is_success=True,
            action_info={"x": 50, "y": 50},
        )

        assert paths["annotated"] is not None
        assert "annotated" in paths["annotated"].replace("\\", "/")
        assert paths["annotated"].endswith(".png")
        # 动作类节点 raw 应为 None
        assert paths["raw"] is None


# ============================================================
# 容错：空 screen 不崩溃
# ============================================================

class TestEdgeCases:
    """空 screen / 无模板时不应崩溃，返回 dict {annotated: None, raw: None}。"""

    def test_empty_screen_template_match_returns_none_paths(self, tmp_path):
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        paths = saver.save_template_debug(
            screen=None,
            template_orig=None,
            template_scaled=None,
            template_name="x",
            is_success=False,
            confidence=0.0,
            threshold=0.8,
            scale_ratio=1.0,
        )
        assert paths == {"annotated": None, "raw": None}

    def test_empty_screen_ocr_returns_none_paths(self, tmp_path):
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        paths = saver.save_ocr_debug(
            screen=np.array([]),
            node_id="x",
            is_success=False,
            texts=[],
            confidences=[],
            boxes=[],
        )
        assert paths == {"annotated": None, "raw": None}


# ============================================================
# A2 (spec 2026-07-30-debug-directory-restructure): 截图命名改为时间前缀
# HHMMSSmmm_<node_id>_<event>.png
# ============================================================

class TestA2TimePrefixFilename:
    """A2: 截图文件名应为 ``HHMMSSmmm_<node_id>_<event>.png`` 格式.

    时间前缀可排序, 与日志时间戳对应, 便于 AI 按时间窗口定位截图.
    旧格式 ``match_{status}_{name}_{timestamp}`` 已废弃.
    """

    def test_template_match_success_filename_format(self, tmp_path):
        """save_template_debug 成功路径文件名应为 HHMMSSmmm_<node_id>_match_success.png."""
        import re
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()
        template = _make_template()

        paths = saver.save_template_debug(
            screen=screen,
            template_orig=template,
            template_scaled=template,
            template_name="t1",
            is_success=True,
            confidence=0.95,
            threshold=0.8,
            scale_ratio=1.0,
            node_id="open_mailbox",
        )

        assert paths["annotated"] is not None
        # 提取文件名 (不含目录和扩展名)
        annotated_name = paths["annotated"].replace("\\", "/").split("/")[-1]
        stem = annotated_name.rsplit(".", 1)[0]
        # 期望格式: HHMMSSmmm_<node_id>_match_success
        # HHMMSSmmm = 9 位数字 (6 位 HHMMSS + 3 位毫秒)
        pattern = r"^\d{6}\d{3}_open_mailbox_match_success$"
        assert re.match(pattern, stem), (
            f"文件名 stem 应为 HHMMSSmmm_open_mailbox_match_success, 实际: {stem}"
        )

    def test_template_match_fail_filename_format(self, tmp_path):
        """save_template_debug 失败路径文件名应为 HHMMSSmmm_<node_id>_match_fail.png."""
        import re
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()
        template = _make_template()

        paths = saver.save_template_debug(
            screen=screen,
            template_orig=template,
            template_scaled=template,
            template_name="t1",
            is_success=False,
            confidence=0.3,
            threshold=0.8,
            scale_ratio=1.0,
            node_id="btn_confirm",
        )

        assert paths["annotated"] is not None
        annotated_name = paths["annotated"].replace("\\", "/").split("/")[-1]
        stem = annotated_name.rsplit(".", 1)[0]
        pattern = r"^\d{9}_btn_confirm_match_fail$"
        assert re.match(pattern, stem), (
            f"文件名 stem 应为 9位数字_btn_confirm_match_fail, 实际: {stem}"
        )

    def test_template_match_raw_filename_matches_annotated(self, tmp_path):
        """save_template_debug raw 和 annotated 文件名 stem 一致 (仅扩展名不同)."""
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()
        template = _make_template()

        paths = saver.save_template_debug(
            screen=screen,
            template_orig=template,
            template_scaled=template,
            template_name="t1",
            is_success=True,
            confidence=0.95,
            threshold=0.8,
            scale_ratio=1.0,
            node_id="node_a",
        )

        annotated_stem = paths["annotated"].replace("\\", "/").split("/")[-1].rsplit(".", 1)[0]
        raw_stem = paths["raw"].replace("\\", "/").split("/")[-1].rsplit(".", 1)[0]
        assert annotated_stem == raw_stem, (
            f"raw 和 annotated 文件名 stem 应一致, annotated={annotated_stem}, raw={raw_stem}"
        )

    def test_ocr_success_filename_format(self, tmp_path):
        """save_ocr_debug 成功路径文件名应为 HHMMSSmmm_<node_id>_ocr_success.png."""
        import re
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()

        paths = saver.save_ocr_debug(
            screen=screen,
            node_id="ocr_step",
            is_success=True,
            texts=["hello"],
            confidences=[0.9],
            boxes=[[10, 20, 30, 40]],
        )

        assert paths["annotated"] is not None
        annotated_name = paths["annotated"].replace("\\", "/").split("/")[-1]
        stem = annotated_name.rsplit(".", 1)[0]
        pattern = r"^\d{9}_ocr_step_ocr_success$"
        assert re.match(pattern, stem), (
            f"文件名 stem 应为 9位数字_ocr_step_ocr_success, 实际: {stem}"
        )

    def test_action_click_filename_format(self, tmp_path):
        """save_action_debug click 文件名应为 HHMMSSmmm_<node_id>_click_success.png."""
        import re
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()

        paths = saver.save_action_debug(
            screen=screen,
            node_id="click_btn",
            node_type="click",
            is_success=True,
            action_info={"x": 50, "y": 50},
        )

        assert paths["annotated"] is not None
        annotated_name = paths["annotated"].replace("\\", "/").split("/")[-1]
        stem = annotated_name.rsplit(".", 1)[0]
        pattern = r"^\d{9}_click_btn_click_success$"
        assert re.match(pattern, stem), (
            f"文件名 stem 应为 9位数字_click_btn_click_success, 实际: {stem}"
        )

    def test_template_match_node_id_sanitized(self, tmp_path):
        """node_id 含特殊字符时应被 sanitize (替换为 _)."""
        import re
        saver = DebugImageSaver(debug_dir=str(tmp_path))
        screen = _make_screen()
        template = _make_template()

        paths = saver.save_template_debug(
            screen=screen,
            template_orig=template,
            template_scaled=template,
            template_name="t1",
            is_success=True,
            confidence=0.95,
            threshold=0.8,
            scale_ratio=1.0,
            node_id="path/to/node",
        )

        annotated_name = paths["annotated"].replace("\\", "/").split("/")[-1]
        stem = annotated_name.rsplit(".", 1)[0]
        # 特殊字符 / 应被替换为 _
        pattern = r"^\d{9}_path_to_node_match_success$"
        assert re.match(pattern, stem), (
            f"node_id 含 / 应被 sanitize 为 _, 实际 stem: {stem}"
        )
