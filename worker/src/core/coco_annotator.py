"""COCO JSON annotation format tool for template management.

Implements MS COCO (Common Objects in Context) JSON Annotation Format
for creating, managing, exporting, and validating image annotations.
Supports compression via zlib to reduce storage overhead.

Reference: ok-script's compress_coco + COCO dataset specification.
"""

import copy
import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class CocoAnnotator:
    """COCO JSON annotation format manager.

    Provides full CRUD operations on COCO-format annotation data,
    including category management, annotation CRUD, import/export,
    compression/decompression, validation, train/val splitting,
    and statistics computation.

    Usage:
        coco = CocoAnnotator.create_empty("img_001", 1920, 1080)
        cat_id = coco.add_category(coco, "character", "game_character")
        ann_id = coco.add_annotation(coco, "img_001", cat_id, [100,200,300,400])
        coco.export_json(coco, "annotations.json")
    """

    def __init__(self, info: dict[str, Any] | None = None):
        """Initialize an empty COCO annotation set

        Args:
            info: Optional dataset info dict (description, version, etc.)
        """
        self._data: dict[str, Any] = {
            "info": info or self._default_info(),
            "licenses": [],
            "images": [],
            "annotations": [],
            "categories": [],
        }
        self._next_ann_id = 1
        self._next_cat_id = 1
        self._next_img_id = 1

    def create_empty(
        self,
        image_id: str | None = None,
        width: int = 0,
        height: int = 0,
        description: str = "",
        version: str = "",
    ) -> dict[str, Any]:
        """Create an empty COCO annotation structure

        Args:
            image_id: Optional initial image ID
            width: Default image width
            height: Default image height
            description: Dataset description
            version: Dataset version string

        Returns:
            Empty COCO format dict ready for annotations
        """
        self._data["info"] = {
            "description": description or "GAF Annotation Dataset",
            "version": version or "1.0",
            "year": 2026,
            "contributor": "GAF",
            "date_created": "",
        }
        self._data["images"] = []
        self._data["annotations"] = []
        self._data["categories"] = []
        self._next_ann_id = 1
        self._next_cat_id = 1
        self._next_img_id = 1

        if image_id:
            self.add_image(self._data, file_name=image_id, width=width, height=height, img_id=image_id)

        return self._data

    def add_category(
        self,
        coco: dict[str, Any],
        name: str,
        supercategory: str = "",
        cat_id: int | None = None,
    ) -> int:
        """Add a new category to the dataset

        Args:
            coco: COCO data dict
            name: Category name (e.g., "character", "button")
            supercategory: Parent supercategory group
            cat_id: Specific ID to use (auto-generated if None)

        Returns:
            Assigned category ID
        """
        if cat_id is None:
            cat_id = self._next_cat_id
            self._next_cat_id += 1
        else:
            self._next_cat_id = max(self._next_cat_id, cat_id + 1)

        category = {
            "id": cat_id,
            "name": name,
            "supercategory": supercategory,
        }

        existing = [c for c in coco["categories"] if c["id"] == cat_id]
        if existing:
            existing[0].update(category)
            logger.debug("Updated category id=%d: %s", cat_id, name)
        else:
            coco["categories"].append(category)
            logger.debug("Added category id=%d: %s", cat_id, name)

        return cat_id

    def add_image(
        self,
        coco: dict[str, Any],
        file_name: str,
        width: int,
        height: int,
        img_id: str | None = None,
    ) -> str:
        """Add an image entry to the dataset

        Args:
            coco: COCO data dict
            file_name: Image file path/name
            width: Image width in pixels
            height: Image height in pixels
            img_id: Specific ID to use (auto-generated if None)

        Returns:
            Assigned image ID string
        """
        if img_id is None:
            img_id = str(self._next_img_id)
            self._next_img_id += 1
        else:
            try:
                next_id = int(img_id) + 1
                self._next_img_id = max(self._next_img_id, next_id)
            except ValueError:
                pass

        image = {
            "id": img_id,
            "file_name": file_name,
            "width": width,
            "height": height,
            "date_captured": "",
        }

        existing = [i for i in coco["images"] if i["id"] == img_id]
        if existing:
            existing[0].update(image)
        else:
            coco["images"].append(image)

        return img_id

    def add_annotation(
        self,
        coco: dict[str, Any],
        image_id: str,
        category_id: int,
        bbox: list[int],
        segmentation: Any | None = None,
        area: float | None = None,
        iscrowd: int = 0,
    ) -> int:
        """Add an annotation to the dataset

        Args:
            coco: COCO data dict
            image_id: Target image ID
            category_id: Category ID from add_category()
            bbox: Bounding box [x, y, width, height]
            segmentation: RLE or polygon segmentation data
            area: Area in pixels (auto-computed from bbox if None)
            iscrowd: Whether annotation covers multiple objects (0/1)

        Returns:
            Assigned annotation ID
        """
        ann_id = self._next_ann_id
        self._next_ann_id += 1

        if area is None:
            area = float(bbox[2] * bbox[3])

        annotation: dict[str, Any] = {
            "id": ann_id,
            "image_id": image_id,
            "category_id": category_id,
            "segmentation": segmentation,
            "area": area,
            "bbox": [int(b) for b in bbox],
            "iscrowd": iscrowd,
        }

        coco["annotations"].append(annotation)
        return ann_id

    def remove_annotation(self, coco: dict[str, Any], ann_id: int) -> bool:
        """Remove an annotation by ID

        Args:
            coco: COCO data dict
            ann_id: Annotation ID to remove

        Returns:
            True if found and removed, False otherwise
        """
        original_len = len(coco["annotations"])
        coco["annotations"] = [
            a for a in coco["annotations"] if a["id"] != ann_id
        ]
        removed = len(coco["annotations"]) < original_len
        if removed:
            logger.debug("Removed annotation id=%d", ann_id)
        return removed

    def get_annotations_for_image(
        self, coco: dict[str, Any], image_id: str
    ) -> list[dict[str, Any]]:
        """Get all annotations for a specific image

        Args:
            coco: COCO data dict
            image_id: Target image ID

        Returns:
            List of annotation dicts
        """
        return [a for a in coco["annotations"] if a["image_id"] == image_id]

    def filter_by_category(
        self, coco: dict[str, Any], category_ids: list[int]
    ) -> dict[str, Any]:
        """Create a filtered copy containing only specified categories

        Args:
            coco: COCO data dict
            category_ids: List of category IDs to keep

        Returns:
            New COCO dict with filtered annotations and categories
        """
        result = copy.deepcopy(coco)
        result["annotations"] = [
            a for a in result["annotations"]
            if a["category_id"] in category_ids
        ]
        result["categories"] = [
            c for c in result["categories"]
            if c["id"] in category_ids
        ]
        used_image_ids = {a["image_id"] for a in result["annotations"]}
        result["images"] = [
            i for i in result["images"] if i["id"] in used_image_ids
        ]
        logger.info(
            "Filtered: %d images, %d annotations, %d categories",
            len(result["images"]), len(result["annotations"]),
            len(result["categories"]),
        )
        return result

    def export_json(
        self, coco: dict[str, Any], path: str, pretty: bool = True
    ) -> bool:
        """Export COCO data to JSON file

        Args:
            coco: COCO data dict
            path: Output file path
            pretty: Whether to indent JSON for readability

        Returns:
            True if export succeeded
        """
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                if pretty:
                    json.dump(coco, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(coco, f, ensure_ascii=False)
            logger.info("Exported COCO JSON to %s (%d bytes)", path, os.path.getsize(path))
            return True
        except OSError as exc:
            logger.error("Failed to export COCO JSON: %s", exc)
            return False

    @staticmethod
    def import_json(path: str) -> dict[str, Any]:
        """Import COCO data from JSON file

        Args:
            path: Input file path

        Returns:
            Loaded COCO data dict
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Imported COCO JSON from %s", path)
        return data

    def compress(self, coco: dict[str, Any]) -> bytes:
        """Compress COCO data to binary format (remove redundant fields)

        Strips metadata and reformats for compact storage.
        Uses zlib for compression.

        Args:
            coco: COCO data dict

        Returns:
            Compressed binary data
        """
        compact = {
            "images": coco.get("images", []),
            "annotations": coco.get("annotations", []),
            "categories": coco.get("categories", []),
        }
        json_bytes = json.dumps(compact, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        import zlib
        compressed = zlib.compress(json_bytes, level=9)
        ratio = len(compressed) / len(json_bytes) * 100 if json_bytes else 0
        logger.info(
            "Compressed COCO: %d -> %d bytes (%.1f%%)",
            len(json_bytes), len(compressed), ratio,
        )
        return compressed

    @staticmethod
    def decompress(data: bytes) -> dict[str, Any]:
        """Decompress binary data back to COCO dict

        Args:
            data: Compressed binary data from compress()

        Returns:
            Restored COCO data dict
        """
        import zlib
        json_bytes = zlib.decompress(data)
        coco = json.loads(json_bytes.decode("utf-8"))
        coco.setdefault("info", {})
        coco.setdefault("licenses", [])
        logger.info("Decompressed COCO: %d bytes -> %d entries", len(data), len(coco.get("annotations", [])))
        return coco

    def validate(self, coco: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate COCO format completeness and consistency

        Checks:
        - Required top-level keys exist
        - All annotation image_ids reference existing images
        - All annotation category_ids reference existing categories
        - Bbox coordinates are non-negative
        - Areas are positive
        - No duplicate IDs

        Args:
            coco: COCO data dict

        Returns:
            (is_valid, error_list) tuple
        """
        errors = []
        required_keys = {"images", "annotations", "categories"}
        for key in required_keys:
            if key not in coco:
                errors.append(f"Missing required key: {key}")

        image_ids = {i["id"] for i in coco.get("images", [])}
        cat_ids = {c["id"] for c in coco.get("categories", [])}
        ann_ids = set()

        for ann in coco.get("annotations", []):
            aid = ann.get("id")
            if aid in ann_ids:
                errors.append(f"Duplicate annotation id: {aid}")
            ann_ids.add(aid)

            if ann.get("image_id") not in image_ids:
                errors.append(
                    f"Annotation {aid} references unknown image: {ann.get('image_id')}"
                )

            if ann.get("category_id") not in cat_ids:
                errors.append(
                    f"Annotation {aid} references unknown category: {ann.get('category_id')}"
                )

            bbox = ann.get("bbox", [])
            if len(bbox) != 4:
                errors.append(f"Annotation {aid} invalid bbox (need 4 values)")
            else:
                for val in bbox:
                    if isinstance(val, (int, float)) and val < 0:
                        errors.append(f"Annotation {aid} negative bbox value: {val}")

            area = ann.get("area", 0)
            if isinstance(area, (int, float)) and area < 0:
                errors.append(f"Annotation {aid} negative area: {area}")

        is_valid = len(errors) == 0
        if is_valid:
            logger.info(
                "COCO validation passed: %d images, %d annotations, %d categories",
                len(image_ids), len(ann_ids), len(cat_ids),
            )
        else:
            logger.warning("COCO validation failed: %d errors", len(errors))
        return is_valid, errors

    def split_train_val(
        self, coco: dict[str, Any], ratio: float = 0.8, seed: int = 42
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Split dataset into training and validation sets by image

        Args:
            coco: COCO data dict
            ratio: Fraction of images for training (0-1)
            seed: Random seed for reproducibility

        Returns:
            (train_coco, val_coco) tuple
        """
        import random
        random.seed(seed)

        images = list(coco.get("images", []))
        random.shuffle(images)

        split_idx = int(len(images) * ratio)
        train_images = {i["id"] for i in images[:split_idx]}
        val_images = {i["id"] for i in images[split_idx:]}

        train = copy.deepcopy(coco)
        train["images"] = [i for i in train["images"] if i["id"] in train_images]
        train["annotations"] = [a for a in train["annotations"] if a["image_id"] in train_images]

        val = copy.deepcopy(coco)
        val["images"] = [i for i in val["images"] if i["id"] in val_images]
        val["annotations"] = [a for a in val["annotations"] if a["image_id"] in val_images]

        logger.info(
            "Split: train=%d images/%d annotations, val=%d images/%d annotations",
            len(train["images"]), len(train["annotations"]),
            len(val["images"]), len(val["annotations"]),
        )
        return train, val

    def stats(self, coco: dict[str, Any]) -> dict[str, Any]:
        """Compute dataset statistics

        Args:
            coco: COCO data dict

        Returns:
            Statistics dict with counts and densities
        """
        images = coco.get("images", [])
        annotations = coco.get("annotations", [])
        categories = coco.get("categories", [])

        total_area = sum(a.get("area", 0) for a in annotations)
        ann_per_image = (
            (len(annotations) / len(images)) if images else 0
        )
        cat_counts: dict[int, int] = {}
        for a in annotations:
            cid = a.get("category_id", 0)
            cat_counts[cid] = cat_counts.get(cid, 0) + 1

        img_areas = {i["id"]: i["width"] * i["height"] for i in images if i.get("width")}
        total_pixel_area = sum(img_areas.values())
        coverage_pct = (total_area / total_pixel_area * 100) if total_pixel_area > 0 else 0

        return {
            "image_count": len(images),
            "annotation_count": len(annotations),
            "category_count": len(categories),
            "total_annotation_area": total_area,
            "avg_annotations_per_image": round(ann_per_image, 2),
            "coverage_percent": round(coverage_pct, 2),
            "category_distribution": cat_counts,
            "dataset_hash": hashlib.md5(
                json.dumps({"ann": len(annotations), "img": len(images)}, sort_keys=True).encode()
            ).hexdigest()[:12],
        }

    @staticmethod
    def _default_info() -> dict[str, Any]:
        """Default dataset info block"""
        return {
            "description": "GAF Annotation Dataset",
            "version": "1.0",
            "year": 2026,
            "contributor": "GAF",
            "date_created": "",
        }
