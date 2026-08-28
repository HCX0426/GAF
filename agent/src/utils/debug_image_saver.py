"""Debug image saver for template match visualization.

Draws ROI rect (blue), match rect (red, success only), center point (green,
success only), confidence/threshold/scale text on the screenshot, then pastes
the template thumbnail (original + scaled) on the right side via
cv2.copyMakeBorder and draws a red line linking the thumbnail to the match
location.

Layout::

    +----------------------------------------+--------+
    | Template: <name>                       |        |
    | Status: SUCCESS|FAIL                   | Orig   |
    | Score: 0.xxxx | Threshold: 0.80        | tpl    |
    | Scale: 0.xxxx | Screen: WxH            |        |
    | ROI(phys): (x,y,w,h)                   +--------+
    | Match(phys): (x,y,w,h) [success only]  |        |
    |                                        | Scaled |
    |     [screenshot with ROI box]          | tpl    |
    |     [match box (success only)]         |        |
    |     [center point (success only)]      |        |
    +----------------------------------------+--------+

Output: ``<debug_dir>/match_{success|fail}_{name}_{HHMMSSmmm}.png``

Reference:
    - BD2-AUTO ``src/auto_control/utils/debug_image_saver.py`` (annotation style)
    - MaaFramework ``source/MaaFramework/Vision/TemplateMatcher.cpp``
      ``draw_result()`` (side-by-side template thumbnail pattern)

Unicode-safe file writing: ``cv2.imencode`` + ``buf.tofile()`` is used instead
of ``cv2.imwrite`` because the latter cannot write to paths containing
non-ASCII characters (e.g. template names like ``主界面``) on Windows.
"""

from __future__ import annotations

import datetime
import logging
import os

import cv2
import numpy as np
from core.constants import NodeType

logger = logging.getLogger(__name__)

# BGR colors for annotations
_COLOR_ROI: tuple[int, int, int] = (255, 0, 0)       # Blue: ROI rect
_COLOR_MATCH: tuple[int, int, int] = (0, 0, 255)     # Red: match rect + connecting line
_COLOR_CENTER: tuple[int, int, int] = (0, 255, 0)    # Green: center point + success status
_COLOR_INFO: tuple[int, int, int] = (255, 255, 255)  # White: info text
_COLOR_FAIL: tuple[int, int, int] = (0, 0, 255)      # Red: fail status text
_COLOR_BORDER: tuple[int, int, int] = (0, 0, 0)      # Black: side-by-side border fill

_BBox = tuple[int, int, int, int]  # (x, y, w, h)

# spec §6.2 — 识别类节点需保留原图（OCR 漏识别 / 模板错位 / 颜色判断失败
# 都要 AI 看真实画面）。动作类节点（click/swipe/key_press/wait）的标注图
# 已包含全部诊断信息，不需要原图。
_RECOGNITION_NODE_TYPES: frozenset[str] = frozenset({
    "template_match",
    "feature_match",
    "ocr",
    "color_detect",
})

# JPEG 压缩质量（spec §6.3）：1920×1080 约 200-400KB，存储成本压到 PNG 的 1/10
_JPEG_QUALITY = 85


class DebugImageSaver:
    """Template match debug visualizer.

    Saves annotated screenshots with side-by-side template thumbnail for
    diagnosing match failures. Disabled by default; enabled via
    ``AgentConfig.debug_mode`` + ``PipelineContext.debug_mode`` plumbing.

    Image-writing failures are non-fatal — they only emit a warning log so
    that the main pipeline flow is never blocked by debug output.
    """

    def __init__(self, debug_dir: str, logger: logging.Logger | None = None) -> None:
        """Initialize the saver.

        Args:
            debug_dir: Directory to write debug PNGs. Created if missing.
            logger: Optional logger; falls back to module logger.
        """
        self.debug_dir = debug_dir
        self.logger = logger or globals()["logger"]
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
        except OSError as exc:
            self.logger.warning("debug_image_saver: makedirs failed: %s", exc)

    def save_template_debug(
        self,
        screen: np.ndarray,
        template_orig: np.ndarray | None,
        template_scaled: np.ndarray | None,
        template_name: str,
        is_success: bool,
        confidence: float,
        threshold: float,
        scale_ratio: float,
        roi_phys: _BBox | None = None,
        match_bbox_phys: _BBox | None = None,
        screen_size: tuple[int, int] | None = None,
        node_id: str = "",
    ) -> dict[str, str | None]:
        """Save an annotated debug image for a template match attempt.

        Args:
            screen: BGR full screenshot (the image the match ran against).
            template_orig: BGR original template (before DPI scaling). May be
                None if template loading failed (only screen is drawn).
            template_scaled: BGR scaled template (what was actually fed to
                cv2.matchTemplate). May be None on legacy path or load failure.
            template_name: Template path or name, used for filename + label.
            is_success: Whether the match exceeded the threshold.
            confidence: Achieved confidence score (0.0~1.0).
            threshold: Configured threshold (0.0~1.0).
            scale_ratio: DPI scale ratio applied to the template.
            roi_phys: Physical-pixel ROI box (x, y, w, h) on the screenshot,
                or None if no ROI was used.
            match_bbox_phys: Physical-pixel match bbox (x, y, w, h), success
                only. None on failure.
            screen_size: Optional (width, height) override; defaults to
                ``screen.shape[1], screen.shape[0]``.
            node_id: A2 新增. 节点 ID, 用于文件名 ``HHMMSSmmm_<node_id>_match_<event>``.
                空时回退到 template_name (向后兼容).

        Returns:
            dict with keys:
                - ``annotated``: PNG path (always set on success)
                - ``raw``: JPEG path (set for recognition nodes; None for actions)
            Both None on failure.
        """
        try:
            if screen is None or screen.size == 0:
                self.logger.warning("debug_image_saver: empty screen, skip")
                return {"annotated": None, "raw": None}

            debug_img = screen.copy()
            if len(debug_img.shape) == 2:
                debug_img = cv2.cvtColor(debug_img, cv2.COLOR_GRAY2BGR)

            screen_h, screen_w = debug_img.shape[:2]
            if screen_size is None:
                screen_size = (screen_w, screen_h)

            # 1. Draw ROI rect (blue) — the search region on the screenshot
            if roi_phys is not None:
                self._draw_bbox(debug_img, roi_phys, _COLOR_ROI, label="ROI")

            # 2. Draw match rect (red) + center point (green) — success only
            match_top_left: tuple[int, int] | None = None
            if is_success and match_bbox_phys is not None:
                match_top_left = self._draw_bbox(
                    debug_img, match_bbox_phys, _COLOR_MATCH, label="Match",
                )
                if match_top_left is not None:
                    mx, my, mw, mh = match_bbox_phys
                    cx = mx + mw // 2
                    cy = my + mh // 2
                    cv2.circle(debug_img, (cx, cy), 4, _COLOR_CENTER, -1, cv2.LINE_AA)

            # 3. Draw top text block with semi-transparent background
            text_lines = [
                f"Template: {template_name}",
                f"Status: {'SUCCESS' if is_success else 'FAIL'}",
                f"Score: {confidence:.4f} | Threshold: {threshold:.2f}",
                f"Scale: {scale_ratio:.4f} | Screen: {screen_size[0]}x{screen_size[1]}",
            ]
            if roi_phys is not None:
                text_lines.append(f"ROI(phys): {roi_phys}")
            if is_success and match_bbox_phys is not None:
                text_lines.append(f"Match(phys): {match_bbox_phys}")

            self._draw_text_block(debug_img, text_lines, is_success=is_success)

            # 4. Side-by-side template thumbnail (right side) — 仅当 screen
            #    高度足够容纳 thumbnail + padding 时才粘贴，否则跳过避免越界。
            #    修复小 screen 场景下的 ValueError（spec 阶段 6 — 任务 2.1）。
            if self._can_fit_thumbnail(screen_h, template_orig, template_scaled):
                debug_img = self._paste_template_thumbnail(
                    debug_img,
                    screen_w=screen_w,
                    screen_h=screen_h,
                    template_orig=template_orig,
                    template_scaled=template_scaled,
                    scale_ratio=scale_ratio,
                    match_top_left=match_top_left,
                )

            # 5. 双保留（spec §6.4）：识别类节点同时保存原图（JPEG q=85）
            #    和标注图（PNG 无损），文件名 stem 一致，靠目录区分用途。
            # A2 (spec 2026-07-30): 文件名改为 HHMMSSmmm_<node_id>_match_<event>
            # 时间前缀可排序, 与日志时间戳对应. 旧格式 match_<status>_<name>_<ts> 废弃.
            timestamp = datetime.datetime.now().strftime("%H%M%S%f")[:-3]
            safe_node_id = self._sanitize_name(node_id) if node_id else self._sanitize_name(template_name)
            status = "success" if is_success else "fail"
            file_stem = f"{timestamp}_{safe_node_id}_match_{status}"

            # 5a. 保存原图（template_match 属识别类）
            raw_path = self._save_raw_image(screen, file_stem, node_type="template_match")

            # 5b. 保存标注图
            annotated_path = self._save_annotated(debug_img, file_stem)
            return {"annotated": annotated_path, "raw": raw_path}
        except Exception as exc:
            self.logger.warning("debug_image_saver save failed: %s", exc, exc_info=True)
            return {"annotated": None, "raw": None}

    def save_ocr_debug(
        self,
        screen: np.ndarray,
        node_id: str,
        is_success: bool,
        texts: list,
        confidences: list,
        boxes: list,
        roi_phys: _BBox | None = None,
        expected_text: str = "",
        engine_name: str = "",
    ) -> dict[str, str | None]:
        """Save an annotated debug image for an OCR node attempt.

        Draws ROI rect (blue), detected text boxes (red) with text labels,
        and a top info block with OCR results.

        Args:
            screen: BGR full screenshot.
            node_id: OCR node ID for filename.
            is_success: Whether OCR met the expected_text condition.
            texts: List of recognized text strings.
            confidences: List of confidence scores (0.0~1.0).
            boxes: List of bounding boxes [x, y, w, h] in physical coords.
            roi_phys: Physical-pixel ROI box, or None if no ROI.
            expected_text: Expected text to match (for fail diagnosis).
            engine_name: OCR engine name used.

        Returns:
            dict with ``annotated`` (PNG) and ``raw`` (JPEG) paths.
            Both None on failure.
        """
        try:
            if screen is None or screen.size == 0:
                return {"annotated": None, "raw": None}

            debug_img = screen.copy()
            if len(debug_img.shape) == 2:
                debug_img = cv2.cvtColor(debug_img, cv2.COLOR_GRAY2BGR)

            # 1. Draw ROI rect (blue)
            if roi_phys is not None:
                self._draw_bbox(debug_img, roi_phys, _COLOR_ROI, label="ROI")

            # 2. Draw text boxes (red) + text labels
            for _i, (text, conf, box) in enumerate(zip(texts, confidences, boxes, strict=False)):
                if box and len(box) >= 4:
                    self._draw_bbox(debug_img, tuple(box), _COLOR_MATCH)
                    # Draw text label below the box
                    bx, by, _bw, bh = int(box[0]), int(box[1]), int(box[2]), int(box[3])
                    label = f"{text[:20]} ({conf:.2f})"
                    cv2.putText(
                        debug_img, label, (bx, by + bh + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, _COLOR_INFO, 1, cv2.LINE_AA,
                    )

            # 3. Draw info block
            text_lines = [
                f"OCR Node: {node_id}",
                f"Status: {'SUCCESS' if is_success else 'FAIL'}",
                f"Engine: {engine_name} | Detected: {len(texts)} lines",
            ]
            if expected_text:
                text_lines.append(f"Expected: {expected_text[:40]}")
            if texts:
                text_lines.append(f"Top: {texts[0][:30]} ({confidences[0]:.2f})" if confidences else "")
            self._draw_text_block(debug_img, text_lines, is_success)

            # 4. 双保留（spec §6.4）：OCR 属识别类，同时保存原图 + 标注图
            # A2 (spec 2026-07-30): 文件名改为 HHMMSSmmm_<node_id>_ocr_<event>
            timestamp = datetime.datetime.now().strftime("%H%M%S%f")[:-3]
            safe_node_id = self._sanitize_name(node_id)
            status = "success" if is_success else "fail"
            file_stem = f"{timestamp}_{safe_node_id}_ocr_{status}"

            # 4a. 保存原图（JPEG q=85）
            raw_path = self._save_raw_image(screen, file_stem, node_type="ocr")

            # 4b. 保存标注图（PNG 无损）
            annotated_path = self._save_annotated(debug_img, file_stem)
            self.logger.info("OCR debug image saved: %s", annotated_path)
            return {"annotated": annotated_path, "raw": raw_path}
        except Exception as exc:
            self.logger.warning("save_ocr_debug failed: %s", exc, exc_info=True)
            return {"annotated": None, "raw": None}

    def save_action_debug(
        self,
        screen: np.ndarray,
        node_id: str,
        node_type: str,
        is_success: bool,
        action_info: dict,
    ) -> dict[str, str | None]:
        """Save a debug image for click/swipe/key_press/wait nodes.

        Draws a marker at the action position (cross for click, arrow for
        swipe, text for key_press) and a top info block.

        Args:
            screen: BGR full screenshot.
            node_id: Node ID for filename.
            node_type: Node type (click/swipe/key_press/wait).
            is_success: Whether the action succeeded.
            action_info: Dict with action details:
                - click: {"x": int, "y": int}
                - swipe: {"start": [x,y], "end": [x,y]}
                - key_press: {"key": str}
                - wait: {"condition": str}

        Returns:
            dict with ``annotated`` (PNG) and ``raw`` (always None — actions
            don't save raw per spec §6.2).
        """
        try:
            if screen is None or screen.size == 0:
                return {"annotated": None, "raw": None}

            debug_img = screen.copy()
            if len(debug_img.shape) == 2:
                debug_img = cv2.cvtColor(debug_img, cv2.COLOR_GRAY2BGR)

            # Draw action marker based on node type
            if node_type == NodeType.CLICK:
                x = action_info.get("x", 0)
                y = action_info.get("y", 0)
                cv2.drawMarker(debug_img, (x, y), _COLOR_MATCH, cv2.MARKER_CROSS, 20, 2, cv2.LINE_AA)
                cv2.circle(debug_img, (x, y), 4, _COLOR_CENTER, -1, cv2.LINE_AA)
            elif node_type == NodeType.SWIPE:
                start = action_info.get("start", [0, 0])
                end = action_info.get("end", [0, 0])
                cv2.arrowedLine(
                    debug_img, tuple(start), tuple(end),
                    _COLOR_MATCH, 2, cv2.LINE_AA, tipLength=0.05,
                )
            elif node_type == NodeType.LONG_PRESS:
                x = action_info.get("x", 0)
                y = action_info.get("y", 0)
                cv2.circle(debug_img, (x, y), 10, _COLOR_MATCH, 2, cv2.LINE_AA)
                cv2.drawMarker(debug_img, (x, y), _COLOR_CENTER, cv2.MARKER_CROSS, 20, 2, cv2.LINE_AA)

            # Draw info block
            status_str = "SUCCESS" if is_success else "FAIL"
            text_lines = [
                f"Node: {node_id} ({node_type})",
                f"Status: {status_str}",
                f"Action: {action_info}",
            ]
            self._draw_text_block(debug_img, text_lines, is_success)

            # Save — 动作类节点不保留原图（spec §6.2），只保存标注图
            # A2 (spec 2026-07-30): 文件名改为 HHMMSSmmm_<node_id>_<node_type>_<event>
            timestamp = datetime.datetime.now().strftime("%H%M%S%f")[:-3]
            safe_node_id = self._sanitize_name(node_id)
            status = "success" if is_success else "fail"
            file_stem = f"{timestamp}_{safe_node_id}_{node_type}_{status}"

            annotated_path = self._save_annotated(debug_img, file_stem)
            self.logger.info("Action debug image saved: %s", annotated_path)
            return {"annotated": annotated_path, "raw": None}
        except Exception as exc:
            self.logger.warning("save_action_debug failed: %s", exc, exc_info=True)
            return {"annotated": None, "raw": None}

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _should_save_raw(node_type: str) -> bool:
        """识别类节点保留原图，动作类节点不保留（spec §6.2）。"""
        return node_type in _RECOGNITION_NODE_TYPES

    @staticmethod
    def _can_fit_thumbnail(
        screen_h: int,
        template_orig: np.ndarray | None,
        template_scaled: np.ndarray | None,
    ) -> bool:
        """判断 screen 高度是否足够容纳 thumbnail + padding。

        修复小 screen 场景下 _paste_template_thumbnail 越界 ValueError
        （spec 阶段 6 — 任务 2.1）。当 screen_h < padding*2 + 最大模板高度
        + gap 时返回 False，调用方跳过 thumbnail 粘贴。

        padding=20, gap_between_thumbs=40（与 _paste_template_thumbnail 一致）。
        """
        padding = 20
        gap = 40
        max_thumb_h = 0
        if template_orig is not None:
            max_thumb_h = max(max_thumb_h, template_orig.shape[0])
        if template_scaled is not None:
            max_thumb_h = max(max_thumb_h, template_scaled.shape[0])
        # 需要容纳: padding + label(12) + orig_h + gap + scaled_h + padding
        required_h = padding + 12 + max_thumb_h + gap + max_thumb_h + padding
        return screen_h >= required_h

    def _save_raw_image(
        self,
        screen: np.ndarray,
        file_stem: str,
        node_type: str,
    ) -> str | None:
        """保存原图为 JPEG q=85 到 screenshots/raw/ 目录（spec §6.4）。

        Args:
            screen: BGR 原始截图（未标注）
            file_stem: 文件名 stem（与标注图一致，仅扩展名不同）
            node_type: 节点类型，用于判断是否需要保留原图

        Returns:
            保存路径，或 None（节点类型不需要原图 / 保存失败）
        """
        if not self._should_save_raw(node_type):
            return None
        try:
            raw_dir = os.path.join(self.debug_dir, "screenshots", "raw")
            os.makedirs(raw_dir, exist_ok=True)
            raw_path = os.path.join(raw_dir, f"{file_stem}.jpg")
            ok, buf = cv2.imencode(".jpg", screen, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
            if not ok:
                self.logger.warning("debug_image_saver: JPEG imencode failed for %s", raw_path)
                return None
            buf.tofile(raw_path)
            return raw_path
        except Exception as exc:
            self.logger.warning("debug_image_saver: save_raw_image failed: %s", exc, exc_info=True)
            return None

    def _save_annotated(self, debug_img: np.ndarray, file_stem: str) -> str | None:
        """保存标注图为 PNG 无损到 screenshots/annotated/ 目录（spec §6.4）。

        Args:
            debug_img: 已标注的 BGR 图像
            file_stem: 文件名 stem（与原图一致）

        Returns:
            保存路径，或 None（保存失败）
        """
        try:
            ann_dir = os.path.join(self.debug_dir, "screenshots", "annotated")
            os.makedirs(ann_dir, exist_ok=True)
            save_path = os.path.join(ann_dir, f"{file_stem}.png")
            ok, buf = cv2.imencode(".png", debug_img)
            if not ok:
                self.logger.warning("debug_image_saver: PNG imencode failed for %s", save_path)
                return None
            buf.tofile(save_path)
            return save_path
        except Exception as exc:
            self.logger.warning("debug_image_saver: save_annotated failed: %s", exc, exc_info=True)
            return None

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Make a template name safe for use in a filename.

        Replaces path separators and spaces with underscores. Non-ASCII
        characters (e.g. Chinese) are preserved — file writing is handled
        unicode-safe via ``buf.tofile()``.
        """
        if not name:
            return "unknown"
        return (
            name.replace("/", "_")
            .replace("\\", "_")
            .replace(" ", "_")
            .replace(":", "_")
        )

    @staticmethod
    def _draw_bbox(
        img: np.ndarray,
        bbox: _BBox,
        color: tuple[int, int, int],
        label: str = "",
    ) -> tuple[int, int] | None:
        """Draw a rectangle with optional label. Returns top-left corner.

        Returns None if the bbox is out of image bounds.
        """
        x, y, w, h = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        if w <= 0 or h <= 0:
            return None
        img_h, img_w = img.shape[:2]
        if x < 0 or y < 0 or x + w > img_w or y + h > img_h:
            return None
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 2, cv2.LINE_AA)
        if label:
            cv2.putText(
                img, label, (x + 4, y + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
            )
        return (x, y)

    @staticmethod
    def _draw_text_block(img: np.ndarray, lines: list, is_success: bool) -> None:
        """Draw a semi-transparent black background with text lines on top."""
        if not lines:
            return
        img_h, img_w = img.shape[:2]
        block_w = min(max(450, img_w // 2), img_w)
        line_h = 22
        block_h = len(lines) * line_h + 12

        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (block_w, block_h), _COLOR_BORDER, -1)
        cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)

        for i, line in enumerate(lines):
            y = 20 + i * line_h
            # Color: line 1 (Status) gets success/fail color; others white.
            color = (_COLOR_CENTER if is_success else _COLOR_FAIL) if i == 1 else _COLOR_INFO
            cv2.putText(
                img, line, (8, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
            )

    @staticmethod
    def _paste_template_thumbnail(
        img: np.ndarray,
        screen_w: int,
        screen_h: int,
        template_orig: np.ndarray | None,
        template_scaled: np.ndarray | None,
        scale_ratio: float,
        match_top_left: tuple[int, int] | None,
    ) -> np.ndarray:
        """Extend img right with black border and paste original + scaled templates.

        Returns the (possibly extended) image. Caller must reassign. Draws a
        red connecting line from the thumbnail's top-left to the match location
        when ``match_top_left`` is provided (success only).
        """
        # Determine thumbnail area dimensions — only the max width is needed
        # to size the right-side extension; heights are read directly from
        # each template below when pasting.
        thumb_w = 0
        if template_orig is not None:
            _th, tw = template_orig.shape[:2]
            thumb_w = max(thumb_w, tw)
        if template_scaled is not None:
            _th, tw = template_scaled.shape[:2]
            thumb_w = max(thumb_w, tw)

        if thumb_w == 0:
            return img  # Nothing to paste

        padding = 20
        gap_between_thumbs = 40  # vertical gap (includes label height)
        thumb_w_padded = thumb_w + padding * 2

        # Extend image right with black border (returns a new array —
        # cv2.copyMakeBorder cannot resize in place).
        extended = cv2.copyMakeBorder(
            img, 0, 0, 0, thumb_w_padded,
            cv2.BORDER_CONSTANT, value=_COLOR_BORDER,
        )

        paste_x = screen_w + padding
        # Original template (top)
        paste_y = padding + 12  # +12 to leave room for label above
        if template_orig is not None:
            th, tw = template_orig.shape[:2]
            extended[paste_y:paste_y + th, paste_x:paste_x + tw] = template_orig
            cv2.putText(
                extended, f"Original {tw}x{th}",
                (paste_x, paste_y - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, _COLOR_INFO, 1, cv2.LINE_AA,
            )
            cv2.rectangle(
                extended, (paste_x - 1, paste_y - 1),
                (paste_x + tw + 1, paste_y + th + 1),
                _COLOR_INFO, 1, cv2.LINE_AA,
            )
            paste_y_bottom = paste_y + th
        else:
            paste_y_bottom = paste_y

        # Scaled template (below original)
        paste_y = paste_y_bottom + gap_between_thumbs
        if template_scaled is not None:
            th, tw = template_scaled.shape[:2]
            extended[paste_y:paste_y + th, paste_x:paste_x + tw] = template_scaled
            cv2.putText(
                extended, f"Scaled {tw}x{th} (ratio={scale_ratio:.4f})",
                (paste_x, paste_y - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, _COLOR_INFO, 1, cv2.LINE_AA,
            )
            cv2.rectangle(
                extended, (paste_x - 1, paste_y - 1),
                (paste_x + tw + 1, paste_y + th + 1),
                _COLOR_INFO, 1, cv2.LINE_AA,
            )

        # Red connecting line from thumbnail top-left to match top-left
        if match_top_left is not None:
            cv2.line(
                extended, (paste_x, padding + 12), match_top_left,
                _COLOR_MATCH, 1, cv2.LINE_AA,
            )

        return extended
