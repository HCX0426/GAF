"""Inspect an OCR debug PNG to verify ROI (blue) vs text (red) box positions.

Reads the image, detects blue and red rectangles via HSV masking, and
prints their bounding boxes so we can confirm whether red boxes fall
inside the blue ROI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np


def find_color_boxes(img_bgr: np.ndarray, lower_hsv, upper_hsv, label: str):
    """Find rectangles of a specific color via HSV masking."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_hsv, upper_hsv)
    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w < 5 or h < 5:  # skip tiny noise
            continue
        boxes.append((x, y, w, h))
    boxes.sort(key=lambda b: b[0])  # sort by x
    print(f"{label}: {len(boxes)} rectangles found")
    for i, (x, y, w, h) in enumerate(boxes):
        print(f"  [{i}] x={x}, y={y}, w={w}, h={h}  ->  ({x},{y}) to ({x+w},{y+h})")
    return boxes


def main():
    if len(sys.argv) < 2:
        print("Usage: python inspect_ocr_debug.py <path-to-ocr-debug.png>")
        sys.exit(1)
    p = Path(sys.argv[1])
    if not p.is_file():
        print(f"File not found: {p}")
        sys.exit(2)
    img = cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        print(f"Failed to read image: {p}")
        sys.exit(3)
    print(f"Image size: {img.shape[1]}x{img.shape[0]} (WxH)")
    print()

    # Blue ROI (Hue ~100-130, high S/V)
    # In OpenCV HSV, Blue hue ~100-130
    lower_blue = np.array([95, 100, 100])
    upper_blue = np.array([135, 255, 255])
    blue_boxes = find_color_boxes(img, lower_blue, upper_blue, "BLUE (ROI)")

    print()
    # Red match boxes (Hue ~0-10 or 170-180, high S/V)
    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 100, 100])
    upper_red2 = np.array([180, 255, 255])
    mask1 = cv2.inRange(cv2.cvtColor(img, cv2.COLOR_BGR2HSV), lower_red1, upper_red1)
    mask2 = cv2.inRange(cv2.cvtColor(img, cv2.COLOR_BGR2HSV), lower_red2, upper_red2)
    red_mask = cv2.bitwise_or(mask1, mask2)
    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    red_boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w < 5 or h < 5:
            continue
        red_boxes.append((x, y, w, h))
    red_boxes.sort(key=lambda b: b[0])
    print(f"RED (Match): {len(red_boxes)} rectangles found")
    for i, (x, y, w, h) in enumerate(red_boxes):
        print(f"  [{i}] x={x}, y={y}, w={w}, h={h}  ->  ({x},{y}) to ({x+w},{y+h})")

    print()
    print("=== Containment check ===")
    if blue_boxes and red_boxes:
        bx, by, bw, bh = blue_boxes[0]
        blue_rect = (bx, by, bx + bw, by + bh)
        for i, (rx, ry, rw, rh) in enumerate(red_boxes):
            red_rect = (rx, ry, rx + rw, ry + rh)
            inside = (red_rect[0] >= blue_rect[0] and red_rect[1] >= blue_rect[1]
                      and red_rect[2] <= blue_rect[2] and red_rect[3] <= blue_rect[3])
            print(f"  Red[{i}] ({red_rect}) inside Blue[0] ({blue_rect})? {inside}")


if __name__ == "__main__":
    main()
