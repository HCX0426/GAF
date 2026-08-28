"""Batch OCR Shared Detection: optimize multi-image OCR via region dedup, mask skipping, and result merging.

Reference: GAF-optimal-solution.md #26 — Batch OCR shared detection from MaaFramework.
Core idea: when multiple images share similar regions, run OCR inference once per unique
region, then distribute results back to each image. This reduces redundant computation
significantly for scenarios like game UI where only small areas change between frames.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class BatchOCRDetector:
    """Batch OCR detector with shared-detection optimization.

    Processes multiple images in a single batch, applying three optimizations:
      1. Region dedup — images with identical regions share one inference call.
      2. Mask skipping  — already-recognized regions are masked out to avoid re-detection.
      3. Result merge   — overlapping detections across batch are merged via IoU NMS.

    The OCR engine is injected via constructor or detect() parameter, ensuring no
    hard-coded dependency on PaddleOCR / RapidOCR / any specific library.

    Expected ocr_engine signature::
        ocr_engine(image: np.ndarray) -> List[Dict[str, Any]]
        # returns [{"text": str, "confidence": float, "bbox": [x,y,w,h]}, ...]
    """

    def __init__(
        self,
        batch_size: int = 8,
        confidence_threshold: float = 0.5,
        merge_iou_threshold: float = 0.5,
        target_size: tuple[int, int] = (640, 640),
        ocr_engine: Callable[[np.ndarray], list[dict[str, Any]]] | None = None,
    ):
        """Initialize BatchOCRDetector.

        Args:
            batch_size: Maximum number of images sent to OCR engine in one call.
            confidence_threshold: Minimum confidence to keep a detection result.
            merge_iou_threshold: IoU threshold for merging duplicate detections.
            target_size: Unified (height, width) for image preprocessing.
            ocr_engine: Default OCR engine callable. Can be overridden in detect().
        """
        self.batch_size = batch_size
        self.confidence_threshold = confidence_threshold
        self.merge_iou_threshold = merge_iou_threshold
        self.target_size = target_size
        self._default_ocr_engine = ocr_engine

    def prepare_batch(self, images: list) -> list:
        """Preprocess a batch of images to unified size and normalization.

        Each input image is resized to ``target_size`` and pixel values are normalized
        to uint8 [0, 255] range. Images that are already numpy arrays are converted
        in-place; PIL Images or file paths are loaded first.

        Args:
            images: List of inputs, each being one of:
                - numpy.ndarray (H, W, C) or (H, W)
                - PIL.Image.Image
                - str (file path, will be loaded via PIL)

        Returns:
            List of preprocessed numpy arrays, all with shape (target_h, target_w, 3).
            Length matches input length; invalid entries become None.

        Raises:
            TypeError: if an element is not a supported type.
        """
        prepared: list = []
        target_h, target_w = self.target_size

        for idx, img in enumerate(images):
            try:
                arr = self._to_numpy(img)
                if arr is None:
                    logger.warning("prepare_batch: image[%d] is None, skipped", idx)
                    prepared.append(None)
                    continue

                arr = self._resize(arr, target_h, target_w)
                arr = self._normalize(arr)
                prepared.append(arr)

            except Exception as exc:
                logger.error("prepare_batch: failed on image[%d]: %s", idx, exc)
                prepared.append(None)

        return prepared

    def detect(
        self,
        images: list,
        ocr_engine: Callable[[np.ndarray], list[dict[str, Any]]] | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Run batch OCR detection with shared-detection optimization.

        Workflow:
          1. Prepare all images via :meth:`prepare_batch`.
          2. Group images by perceptual hash to find identical/similar regions.
          3. For each unique region group, call OCR engine **once**.
          4. Apply mask to skip regions already recognized in prior groups.
          5. Merge overlapping results via IoU-based NMS.
          6. Filter by confidence threshold and return per-image result lists.

        Args:
            images: Raw image inputs (same types accepted by :meth:`prepare_batch`).
            ocr_engine: OCR engine callable overriding the default. Signature::

                engine(image: np.ndarray) -> List[Dict[str, Any]]

                Each dict must contain: "text" (str), "confidence" (float),
                "bbox" (list of 4 ints/floats [x, y, w, h]).

        Returns:
            List of per-image result lists. Outer length == len(images).
            Each inner element is:: {"text": str, "confidence": float, "bbox": [x,y,w,h]}.
            Images that failed preprocessing return empty lists.
        """
        engine = ocr_engine or self._default_ocr_engine
        if engine is None:
            logger.error("detect: no OCR engine provided")
            return [[] for _ in images]

        prepared = self.prepare_batch(images)
        n = len(prepared)

        region_groups: dict[int, list[int]] = self._group_by_region(prepared)
        logger.debug(
            "detect: %d images grouped into %d unique region(s)", n, len(region_groups)
        )

        all_results: list[list[dict[str, Any]]] = [[] for _ in range(n)]
        global_mask: np.ndarray | None = None

        sorted_group_keys = sorted(region_groups.keys(), key=lambda k: len(region_groups[k]), reverse=True)

        for group_key in sorted_group_keys:
            indices = region_groups[group_key]
            rep_idx = indices[0]
            rep_image = prepared[rep_idx]

            if rep_image is None:
                continue

            masked_image = self._apply_mask(rep_image, global_mask)

            try:
                raw_detections = engine(masked_image)
            except Exception as exc:
                logger.error("detect: OCR inference failed for group %s: %s", group_key, exc)
                continue

            filtered = [
                d for d in raw_detections
                if d.get("confidence", 0.0) >= self.confidence_threshold
            ]

            merged = self._merge_detections(filtered)

            for idx in indices:
                all_results[idx].extend(merged)

            if merged and global_mask is not None:
                global_mask = self._update_mask(global_mask, merged)

        final_results: list[list[dict[str, Any]]] = []
        for i in range(n):
            deduped = self._merge_detections(all_results[i])
            final_results.append(deduped)

        total = sum(len(r) for r in final_results)
        logger.info("detect: %d images -> %d total detections", n, total)
        return final_results

    def _to_numpy(self, img: Any) -> np.ndarray | None:
        """Convert various image formats to numpy ndarray.

        Args:
            img: numpy array, PIL Image, or file path string.

        Returns:
            numpy array in (H, W, 3) uint8 format, or None on failure.
        """
        if isinstance(img, np.ndarray):
            arr = img.copy()
            if arr.ndim == 2:
                arr = np.stack([arr] * 3, axis=-1)
            elif arr.ndim == 3 and arr.shape[2] == 4:
                arr = arr[:, :, :3]
            if arr.dtype != np.uint8:
                arr = np.clip(arr, 0, 255).astype(np.uint8)
            return arr

        if self._is_pil_image(img):
            arr = np.array(img.convert("RGB"))
            return arr.astype(np.uint8)

        if isinstance(img, str):
            try:
                from PIL import Image

                pil_img = Image.open(img).convert("RGB")
                arr = np.array(pil_img)
                return arr.astype(np.uint8)
            except Exception as exc:
                logger.error("_to_numpy: failed to load image path '%s': %s", img, exc)
                return None

        logger.warning("_to_numpy: unsupported type %s", type(img).__name__)
        return None

    @staticmethod
    def _is_pil_image(obj: Any) -> bool:
        """Check if object is a PIL Image without importing PIL at module level."""
        try:
            from PIL import Image

            return isinstance(obj, Image.Image)
        except ImportError:
            return False

    @staticmethod
    def _resize(arr: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
        """Resize image to target dimensions using bilinear interpolation.

        Args:
            arr: Input image array (H, W, C).
            target_h: Target height in pixels.
            target_w: Target width in pixels.

        Returns:
            Resized array with shape (target_h, target_w, C).
        """
        h, w = arr.shape[:2]
        if h == target_h and w == target_w:
            return arr

        try:
            import cv2

            return cv2.resize(arr, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        except ImportError:
            pass

        try:
            from PIL import Image

            pil_img = Image.fromarray(arr)
            pil_img = pil_img.resize((target_w, target_h), Image.BILINEAR)
            return np.array(pil_img)
        except ImportError:
            pass

        logger.warning("_resize: neither cv2 nor PIL available, using numpy resize")
        return _numpy_resize(arr, target_h, target_w)

    @staticmethod
    def _normalize(arr: np.ndarray) -> np.ndarray:
        """Normalize pixel values to valid uint8 range [0, 255].

        Args:
            arr: Input image array.

        Returns:
            Normalized uint8 array.
        """
        if arr.dtype != np.uint8:
            arr = np.clip(np.asarray(arr, dtype=np.float64), 0, 255).astype(np.uint8)
        return arr

    def _group_by_region(self, prepared: list) -> dict[int, list[int]]:
        """Group image indices by perceptual hash of their content.

        Images with identical hashes are considered to share the same visual region
        and will only trigger one OCR inference call.

        Args:
            prepared: List of preprocessed numpy arrays (may contain None).

        Returns:
            Dict mapping hash value -> list of original image indices.
        """
        groups: dict[int, list[int]] = {}

        for idx, arr in enumerate(prepared):
            h = hash(id(arr)) if arr is None else self._perceptual_hash(arr)

            if h not in groups:
                groups[h] = []
            groups[h].append(idx)

        return groups

    @staticmethod
    def _perceptual_hash(arr: np.ndarray) -> int:
        """Compute a lightweight perceptual hash for an image array.

        Uses a simple average-hash approach: resize to 8x8, compute mean,
        generate 64-bit fingerprint based on pixel-wise above/below-mean comparison.

        Args:
            arr: Input image array (H, W, C).

        Returns:
            Integer hash value.
        """
        try:
            import cv2

            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if arr.ndim == 3 else arr
            tiny = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
            avg = tiny.mean()
            bits = (tiny > avg).flatten().astype(np.int64)
            fingerprint = 0
            for bit in bits:
                fingerprint = (fingerprint << 1) | int(bit)
            return int(fingerprint)
        except ImportError:
            pass

        try:
            from PIL import Image

            pil_img = Image.fromarray(arr)
            gray = pil_img.convert("L") if pil_img.mode != "L" else pil_img
            tiny = gray.resize((8, 8), Image.LANCZOS)
            pixels = list(tiny.getdata())
            avg = sum(pixels) / len(pixels)
            fingerprint = 0
            for p in pixels:
                fingerprint = (fingerprint << 1) | (1 if p > avg else 0)
            return fingerprint
        except ImportError:
            pass

        arr_flat = arr.flatten()
        chunk_size = max(1, len(arr_flat) // 64)
        sampled = arr_flat[::chunk_size][:64]
        avg = np.mean(sampled) if len(sampled) > 0 else 0
        fingerprint = 0
        for val in sampled:
            fingerprint = (fingerprint << 1) | (1 if val > avg else 0)
        return int(fingerprint)

    @staticmethod
    def _apply_mask(image: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
        """Apply a binary mask to black out already-processed regions.

        Where mask is True (or > 0), corresponding pixels in the output image
        are set to pure black (0), preventing the OCR engine from re-detecting
        text in those areas.

        Args:
            image: Original image array (H, W, C).
            mask: Binary mask (H, W) of same spatial dims, or None to skip masking.

        Returns:
            Masked image copy, or original copy if mask is None.
        """
        if mask is None:
            return image.copy()

        result = image.copy()
        if mask.shape[:2] != image.shape[:2]:
            logger.warning(
                "_apply_mask: mask shape %s mismatch image shape %s, skipping",
                mask.shape, image.shape[:2],
            )
            return result

        mask_bool = mask.astype(bool) if mask.dtype != bool else mask
        for c in range(result.shape[2]):
            result[:, :, c][mask_bool] = 0
        return result

    @staticmethod
    def _update_mask(
        mask: np.ndarray, detections: list[dict[str, Any]]
    ) -> np.ndarray:
        """Update the exclusion mask with newly detected bounding boxes.

        Marks the area covered by each detection as "already processed" so that
        subsequent region groups skip these areas.

        Args:
            mask: Existing binary mask (H, W), will be modified in-place then returned.
            detections: List of detection dicts with "bbox" keys.

        Returns:
            Updated mask with new regions marked.
        """
        updated = mask.copy()
        h, w = mask.shape[:2]

        for det in detections:
            bbox = det.get("bbox")
            if not bbox or len(bbox) < 4:
                continue

            x, y, bw, bh = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            x1 = max(0, min(x, w))
            y1 = max(0, min(y, h))
            x2 = max(0, min(x + bw, w))
            y2 = max(0, min(y + bh, h))

            updated[y1:y2, x1:x2] = 1

        return updated

    def _merge_detections(
        self, detections: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Merge overlapping detections using IoU-based Non-Maximum Suppression.

        When multiple bounding boxes overlap significantly (IoU >= threshold),
        only the one with highest confidence is kept. This prevents duplicate
        text detections from the same region appearing multiple times.

        Args:
            detections: Raw detection list, each dict has "text", "confidence", "bbox".

        Returns:
            Deduplicated and merged detection list, sorted by confidence descending.
        """
        if not detections:
            return []

        if len(detections) <= 1:
            return self._sanitize_detection(detections[0]) if detections else []

        scored = []
        for det in detections:
            conf = det.get("confidence", 0.0)
            bbox = det.get("bbox")
            if bbox and len(bbox) >= 4:
                scored.append((conf, det))

        scored.sort(key=lambda x: x[0], reverse=True)

        keep: list[dict[str, Any]] = []
        suppressed = set()

        for i, (conf_i, det_i) in enumerate(scored):
            if i in suppressed:
                continue

            best = det_i.copy()
            bbox_i = det_i.get("bbox", [0, 0, 0, 0])

            for j, (conf_j, det_j) in enumerate(scored):
                if j <= i or j in suppressed:
                    continue

                bbox_j = det_j.get("bbox", [0, 0, 0, 0])
                iou = self._compute_iou(bbox_i, bbox_j)

                if iou >= self.merge_iou_threshold:
                    suppressed.add(j)
                    if conf_j > conf_i:
                        best = det_j.copy()
                        bbox_i = best.get("bbox", bbox_i)

            keep.append(best)

        sanitized = [self._sanitize_detection(d) for d in keep]
        sanitized.sort(key=lambda d: d.get("confidence", 0.0), reverse=True)
        return sanitized

    @staticmethod
    def _compute_iou(
        box_a: list[float], box_b: list[float]
    ) -> float:
        """Compute Intersection over Union between two bounding boxes.

        Both boxes are expected in [x, y, w, h] format.

        Args:
            box_a: First bounding box [x, y, w, h].
            box_b: Second bounding box [x, y, w, h].

        Returns:
            IoU value in range [0.0, 1.0].
        """
        ax, ay, aw, ah = box_a[0], box_a[1], box_a[2], box_a[3]
        bx, by, bw, bh = box_b[0], box_b[1], box_b[2], box_b[3]

        a_x2, a_y2 = ax + aw, ay + ah
        b_x2, b_y2 = bx + bw, by + bh

        inter_x1 = max(ax, bx)
        inter_y1 = max(ay, by)
        inter_x2 = min(a_x2, b_x2)
        inter_y2 = min(a_y2, b_y2)

        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        area_a = aw * ah
        area_b = bw * bh
        union_area = area_a + area_b - inter_area

        if union_area <= 0:
            return 0.0

        return float(inter_area / union_area)

    @staticmethod
    def _sanitize_detection(det: dict[str, Any]) -> dict[str, Any]:
        """Ensure a detection dict has all required fields with correct types.

        Args:
            det: Raw detection dictionary.

        Returns:
            Sanitized dict with "text" (str), "confidence" (float), "bbox" ([x,y,w,h]).
        """
        text = str(det.get("text", ""))
        confidence = float(det.get("confidence", 0.0))
        raw_bbox = det.get("bbox", [0, 0, 0, 0])

        if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
            bbox = [float(raw_bbox[0]), float(raw_bbox[1]),
                    float(raw_bbox[2]), float(raw_bbox[3])]
        elif isinstance(raw_bbox, dict):
            bbox = [
                float(raw_bbox.get("x", raw_bbox.get("x1", 0))),
                float(raw_bbox.get("y", raw_bbox.get("y1", 0))),
                float(raw_bbox.get("w", raw_bbox.get("width", 0))),
                float(raw_bbox.get("h", raw_bbox.get("height", 0))),
            ]
        else:
            bbox = [0.0, 0.0, 0.0, 0.0]

        return {
            "text": text,
            "confidence": confidence,
            "bbox": bbox,
        }


def _numpy_resize(arr: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """Fallback resize using only numpy (nearest-neighbor, lower quality).

    Used when neither cv2 nor PIL is available. Performs simple nearest-neighbor
    interpolation by indexing into the source array.

    Args:
        arr: Source array (H, W, C).
        target_h: Target height.
        target_w: Target width.

    Returns:
        Resized array (target_h, target_w, C).
    """
    src_h, src_w = arr.shape[:2]
    row_indices = np.linspace(0, src_h - 1, target_h).astype(int)
    col_indices = np.linspace(0, src_w - 1, target_w).astype(int)
    if arr.ndim == 3:
        return np.take(np.take(arr, col_indices, axis=1), row_indices, axis=0)
    return np.take(np.take(arr, col_indices, axis=1), row_indices, axis=0)
