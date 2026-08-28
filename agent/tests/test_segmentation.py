"""SegmentationEngine unit tests.

Covers both SAM and U2-Net branches as well as the ``SegmentedRegion``
dataclass. cv2 / numpy are real (installed in the gaf env); SAM model
is mocked because ``ultralytics`` is not installed (``_SAM_AVAILABLE``
is False at runtime).
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from core.segmentation import SegmentationEngine, SegmentedRegion

pytestmark = pytest.mark.unit


@pytest.fixture
def u2net_engine():
    """Engine in u2net mode. _U2NET_AVAILABLE is True in the gaf env, so
    the engine initializes its internal marker and is ready to segment."""
    return SegmentationEngine(mode="u2net")


def _solid_square_image(size: int = 100) -> np.ndarray:
    """Build a BGR image with a bright square on a dark background.

    Produces a strong contour for cv2.findContours in the u2net path.
    """
    img = np.zeros((size, size, 3), dtype=np.uint8)
    img[25:75, 25:75] = 255
    return img


class TestSegmentedRegionDataclass:
    """Verify SegmentedRegion dataclass field handling."""

    def test_fields_assigned(self):
        mask = np.zeros((10, 10), dtype=np.uint8)
        region = SegmentedRegion(
            label="region_0",
            mask=mask,
            bbox=(1, 2, 3, 4),
            confidence=0.9,
        )
        assert region.label == "region_0"
        assert region.bbox == (1, 2, 3, 4)
        assert region.confidence == 0.9
        assert np.array_equal(region.mask, mask)


class TestSegmentationEngineInit:
    """Verify initialization across modes."""

    def test_init_u2net_is_available(self, u2net_engine):
        # Real env has cv2 + dnn_superres, so u2net engine is available
        assert u2net_engine.is_available is True
        assert u2net_engine.mode == "u2net"

    def test_init_sam_unavailable_without_ultralytics(self):
        # ultralytics is not installed in the gaf env, so SAM mode cannot
        # initialize the model — engine reports not available.
        eng = SegmentationEngine(mode="sam", model_path="/dev/null")
        assert eng.is_available is False

    def test_init_unknown_mode_is_not_available(self):
        eng = SegmentationEngine(mode="mystery")
        assert eng.is_available is False
        assert eng.mode == "mystery"


class TestSegmentationEngineSegment:
    """Verify segment() dispatch and edge cases."""

    def test_segment_unknown_mode_returns_empty(self):
        eng = SegmentationEngine(mode="mystery")
        # Even with a valid image, unknown mode short-circuits to []
        result = eng.segment(_solid_square_image())
        assert result == []

    def test_segment_unavailable_returns_empty(self):
        # SAM path is unavailable in this env — segment() must return []
        eng = SegmentationEngine(mode="sam", model_path="/dev/null")
        assert eng.segment(_solid_square_image()) == []

    def test_segment_u2net_returns_at_least_one_region(self, u2net_engine):
        # Solid square on black background yields a contour > 100px area,
        # so the u2net path should detect it.
        regions = u2net_engine.segment(_solid_square_image())
        assert len(regions) >= 1
        first = regions[0]
        assert isinstance(first, SegmentedRegion)
        # bbox is (x, y, w, h) — must be positive for a real contour
        x, y, w, h = first.bbox
        assert w > 0 and h > 0
        # mask shape matches image height/width
        assert first.mask.shape == (100, 100)

    def test_segment_u2net_target_labels_filters_out(self, u2net_engine):
        # target_labels is a deny-by-default filter: labels not in the list
        # are excluded. With an unrelated label, nothing should be returned.
        regions = u2net_engine.segment(
            _solid_square_image(),
            target_labels=["region_999"],
        )
        assert regions == []

    def test_segment_u2net_regions_have_fixed_confidence(self, u2net_engine):
        # The u2net path hardcodes confidence=0.85 on every emitted region
        # and does NOT filter by confidence_threshold (unlike SAM).
        # This test documents that invariant: regions survive any threshold.
        low = u2net_engine.segment(_solid_square_image(), confidence_threshold=0.5)
        high = u2net_engine.segment(_solid_square_image(), confidence_threshold=0.99)
        assert len(low) >= 1
        # No filtering applied — same count regardless of threshold
        assert len(high) == len(low)
        for region in high:
            assert region.confidence == 0.85

    def test_segment_u2net_handles_invalid_image_gracefully(self, u2net_engine):
        # cv2.cvtColor on a 2-D array raises; engine must swallow and return []
        result = u2net_engine.segment(np.zeros((10, 10), dtype=np.uint8))
        assert result == []


class TestSegmentationEngineSamMocked:
    """Exercise the SAM branch by injecting a mocked model directly.

    ``_SAM_AVAILABLE`` is False in the gaf env, so we patch the
    instance's ``_model`` and ``is_available`` to drive _segment_sam.
    """

    def test_sam_segment_with_mocked_model_returns_regions(self):
        eng = SegmentationEngine(mode="sam", model_path="fake")
        # Bypass availability gate and inject a fake SAM result
        eng._model = MagicMock()
        with patch.object(type(eng), "is_available", new=True):
            # Build a fake result object exposing .masks and .boxes
            fake_mask = np.ones((10, 10), dtype=np.uint8)
            fake_boxes = MagicMock()
            # Source uses `i < len(boxes)` — configure __len__ so the
            # cls/conf/xyxy branch is taken instead of the fallback.
            fake_boxes.__len__ = MagicMock(return_value=1)
            fake_boxes.cls = [0]
            fake_boxes.conf = [0.9]
            # xyxy[i].tolist() is called — use numpy array (has .tolist())
            fake_boxes.xyxy = np.array([[10, 10, 50, 50]])
            fake_result = MagicMock()
            fake_result.masks.data = [fake_mask]
            fake_result.boxes = fake_boxes
            eng._model.return_value = [fake_result]

            regions = eng.segment(_solid_square_image())
        assert len(regions) == 1
        assert regions[0].label == "region_0"
        assert regions[0].confidence == 0.9
        # bbox derived from xyxy [10,10,50,50] -> (x, y, w, h) = (10, 10, 40, 40)
        assert regions[0].bbox == (10, 10, 40, 40)

    def test_sam_segment_skips_result_when_masks_none(self):
        eng = SegmentationEngine(mode="sam", model_path="fake")
        eng._model = MagicMock()
        with patch.object(type(eng), "is_available", new=True):
            fake_result = MagicMock()
            fake_result.masks = None
            eng._model.return_value = [fake_result]
            regions = eng.segment(_solid_square_image())
        assert regions == []
