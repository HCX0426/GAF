"""Screenshot method diagnostic — try every capture method + run template_match.

When template_match confidence is low, the root cause is often the screenshot
method itself (wrong content, occluded window, chrome offset). This utility
iterates through all available capture methods (WGC, DXGI, GDI, PrintWindow),
captures a frame with each, runs a template_match against it, and reports
which method gives the highest confidence.

Usage:
    conda run -n gaf python -m utils.screenshot_diagnostic \\
        --template "BrownDust-II/templates/public/主界面.png" \\
        --roi 1720,20,120,70 \\
        --base-res 1920,1080

AI auto-analysis contract (per project_rules.md §4.8):
    When debug_mode=True and template_match fails, the AI should run this
    diagnostic before notifying the user. If any method gives confidence ≥
    threshold, the AI should switch the device to that method and retry. Only
    if ALL methods fail should the AI notify the user with the full report.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# Add agent/src to path when run as script
AGENT_SRC = Path(__file__).resolve().parent.parent
if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

# Apply DPI awareness BEFORE any GDI/PrintWindow capture — otherwise GDI
# returns DPI-virtualized logical pixels (e.g. 1024x576) instead of physical
# pixels (1536x864), and coord_transformer's scale_ratio becomes wrong.
# Importing platforms.windows.dpi triggers apply_dpi_awareness() at module load.
import contextlib  # noqa: E402

from platforms.windows import dpi  # noqa: F401, E402

logger = logging.getLogger(__name__)


@dataclass
class MethodResult:
    """Single screenshot method's diagnostic result."""
    method: str
    available: bool = False
    error_msg: str = ""
    screenshot_shape: tuple[int, int] | None = None  # (h, w)
    screenshot_is_blank: bool = True
    mean_pixel: float = 0.0
    capture_ms: float = 0.0
    template_match_confidence: float = 0.0
    template_match_success: bool = False
    debug_image_path: str = ""


@dataclass
class DiagnosticReport:
    """Full diagnostic report across all methods."""
    device_id: str = ""
    device_name: str = ""
    hwnd: int = 0
    client_rect: tuple[int, int] = (0, 0)  # (w, h)
    window_rect: tuple[int, int] = (0, 0)  # (w, h)
    base_res: tuple[int, int] = (0, 0)  # (w, h)
    results: list[MethodResult] = field(default_factory=list)

    def best_method(self) -> MethodResult | None:
        """Return the method with highest template_match confidence."""
        if not self.results:
            return None
        working = [r for r in self.results if r.available and not r.screenshot_is_blank]
        if not working:
            return None
        return max(working, key=lambda r: r.template_match_confidence)

    def summary_table(self) -> str:
        """Render results as a text table for logging/CLI output."""
        lines = []
        lines.append("=" * 100)
        lines.append(f"Device: {self.device_name} (id={self.device_id}, hwnd={self.hwnd})")
        lines.append(
            f"Client rect: {self.client_rect[0]}x{self.client_rect[1]}  "
            f"Window rect: {self.window_rect[0]}x{self.window_rect[1]}  "
            f"Base res: {self.base_res[0]}x{self.base_res[1]}"
        )
        lines.append("-" * 100)
        header = f"{'Method':<14} {'Avail':<6} {'Shape':<14} {'Blank':<6} {'CapMs':<7} {'Conf':<8} {'Match':<6} {'Error'}"
        lines.append(header)
        lines.append("-" * 100)
        for r in self.results:
            shape_str = f"{r.screenshot_shape[1]}x{r.screenshot_shape[0]}" if r.screenshot_shape else "-"
            lines.append(
                f"{r.method:<14} "
                f"{'yes' if r.available else 'no':<6} "
                f"{shape_str:<14} "
                f"{'yes' if r.screenshot_is_blank else 'no':<6} "
                f"{r.capture_ms:<7.1f} "
                f"{r.template_match_confidence:<8.4f} "
                f"{'ok' if r.template_match_success else 'fail':<6} "
                f"{r.error_msg[:40]}"
            )
        lines.append("=" * 100)
        best = self.best_method()
        if best:
            lines.append(
                f"BEST: {best.method} (confidence={best.template_match_confidence:.4f}, "
                f"shape={best.screenshot_shape[1]}x{best.screenshot_shape[0]})"
            )
        else:
            lines.append("BEST: NONE (all methods failed or blank)")
        return "\n".join(lines)


def _is_blank(img: np.ndarray) -> tuple[bool, float]:
    """Return (is_blank, mean_pixel). Blank = near-uniform color (std < 5)."""
    if img is None or img.size == 0:
        return True, 0.0
    mean = float(img.mean())
    std = float(img.std())
    return std < 5.0, mean


def _run_template_match(
    screen: np.ndarray,
    template_path: str,
    roi_base: tuple[int, int, int, int],
    base_res: tuple[int, int],
    debug_dir: str | None,
    method_name: str,
) -> tuple[float, bool, str]:
    """Run template_match against screen, return (confidence, success, debug_path).

    Uses the same coord_transformer + template_match logic as the production
    pipeline so confidence numbers are directly comparable.
    """
    from engine.context import PipelineContext
    from engine.nodes.template_match import TemplateMatchNode

    # Build a dummy device-like object that returns the pre-captured screen.
    # This avoids re-capturing and lets us test the existing screen.
    class _StaticDevice:
        device_id = "diagnostic"
        name = "diagnostic"
        def capture_screen(self):
            return screen

    # Construct a transformer using the screen's actual size as target_phys_size.
    # We can't use build_transformer(device) because the device's hwnd/rect may
    # not match the screen we already captured. Instead, build a minimal
    # transformer inline using the real RuntimeDisplayContext dataclass fields
    # (see utils/display_context.py — fields are *_width/*_height, not *_res).
    from utils.coord_transformer import CoordinateTransformer
    from utils.display_context import RuntimeDisplayContext

    screen_h, screen_w = screen.shape[:2]
    base_w, base_h = base_res
    # Use the screen's own size as client_physical — this is what the
    # production pipeline assumes (screenshot pixels == client-physical pixels).
    rdc = RuntimeDisplayContext(
        original_base_width=base_w,
        original_base_height=base_h,
        hwnd=0,
        is_fullscreen=False,
        dpi_scale=1.0,
        client_logical_width=screen_w,
        client_logical_height=screen_h,
        client_physical_width=screen_w,
        client_physical_height=screen_h,
        screen_physical_width=screen_w,
        screen_physical_height=screen_h,
        client_screen_origin_x=0,
        client_screen_origin_y=0,
    )
    transformer = CoordinateTransformer(rdc)

    debug_dir_method = os.path.join(debug_dir, f"diag_{method_name}") if debug_dir else None
    context = PipelineContext(
        device=_StaticDevice(),
        coord_transformer=transformer,
        display_context=rdc,
        debug_mode=bool(debug_dir_method),
        debug_dir=debug_dir_method or "./debug",
    )

    node = TemplateMatchNode(
        id=f"diag_{method_name}",
        config={
            "template": template_path,
            "threshold": 0.8,
            "roi": list(roi_base),
            "roi_coord_type": "base",
            "click_on_match": False,
        },
    )
    result = node.execute(context)

    debug_path = ""
    if debug_dir_method and os.path.exists(debug_dir_method):
        files = sorted(Path(debug_dir_method).glob("match_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            debug_path = str(files[0])

    confidence = 0.0
    if result.data and "confidence" in result.data:
        confidence = float(result.data["confidence"])
    elif result.error_msg and "置信度" in result.error_msg:
        # Parse "模板匹配置信度 0.2694 低于阈值 0.8"
        with contextlib.suppress(IndexError, ValueError):
            confidence = float(result.error_msg.split("置信度")[1].split("低于")[0].strip())

    return confidence, result.success, debug_path


def run_diagnostic(
    device,
    template_path: str,
    roi_base: tuple[int, int, int, int],
    base_res: tuple[int, int] = (1920, 1080),
    debug_dir: str | None = None,
    methods: list[str] | None = None,
) -> DiagnosticReport:
    """Run screenshot method diagnostic on a device.

    Args:
        device: WindowsDevice (must be connected — hwnd bound).
        template_path: Template path (relative to GAF/resources/ or absolute).
        roi_base: ROI in base-res coords (x, y, w, h).
        base_res: Base resolution (w, h) for coord_transformer.
        debug_dir: If set, save debug images per method.
        methods: Override method list (default: all 4 in fallback order).

    Returns:
        DiagnosticReport with one MethodResult per method.
    """

    from platforms.windows.screenshot import ScreenshotManager

    report = DiagnosticReport(
        device_id=device.device_id,
        device_name=device.name,
        hwnd=getattr(device, "hwnd", 0) or 0,
        base_res=base_res,
    )

    # Record window/client rects for diagnostic
    if report.hwnd:
        from platforms.windows.window import get_client_rect, get_window_rect

        wr = get_window_rect(report.hwnd)
        if wr is not None:
            report.window_rect = (wr[2] - wr[0], wr[3] - wr[1])
        cr = get_client_rect(report.hwnd)
        if cr is not None:
            report.client_rect = (cr[2] - cr[0], cr[3] - cr[1])

    if methods is None:
        methods = [ScreenshotManager.WGC, ScreenshotManager.DXGI,
                   ScreenshotManager.GDI, ScreenshotManager.PRINTWINDOW]

    for method in methods:
        result = MethodResult(method=method)
        logger.info("Testing method: %s", method)
        try:
            # Build a fresh ScreenshotManager for each method to avoid
            # state leakage. client_only=True so screenshot matches the
            # coord_transformer's client-physical coordinate system.
            mgr = ScreenshotManager(
                hwnd=report.hwnd, method=method, client_only=True,
            )
            t0 = time.perf_counter()
            screen = mgr.capture()
            result.capture_ms = (time.perf_counter() - t0) * 1000.0
            mgr.release()

            if screen is None:
                result.error_msg = "capture returned None"
                report.results.append(result)
                continue

            # Check if the requested method actually worked or fell back to
            # a different method. ScreenshotManager.capture() silently falls
            # back through wgc→dxgi→gdi→printwindow when the primary method
            # fails. If fallback occurred, the method itself is NOT available
            # and auto-heal must not switch the device to it (otherwise every
            # subsequent capture wastes time retrying the broken method before
            # falling back, and may produce inconsistent screenshot sizes).
            actual_method = getattr(mgr, "_best_method", None)
            if actual_method and actual_method != method:
                result.error_msg = (
                    f"primary method failed, fell back to {actual_method}"
                )
                result.available = False
                logger.info(
                    "Method %s unavailable (fell back to %s), marking as unusable",
                    method, actual_method,
                )
                report.results.append(result)
                continue

            result.available = True
            result.screenshot_shape = screen.shape[:2]
            blank, mean = _is_blank(screen)
            result.screenshot_is_blank = blank
            result.mean_pixel = mean

            if blank:
                result.error_msg = f"blank frame (mean={mean:.1f})"
                report.results.append(result)
                continue

            # Run template_match against this screenshot
            try:
                conf, ok, dbg = _run_template_match(
                    screen=screen,
                    template_path=template_path,
                    roi_base=roi_base,
                    base_res=base_res,
                    debug_dir=debug_dir,
                    method_name=method,
                )
                result.template_match_confidence = conf
                result.template_match_success = ok
                result.debug_image_path = dbg
            except Exception as exc:
                result.error_msg = f"template_match failed: {exc}"

        except Exception as exc:
            result.error_msg = f"capture failed: {exc}"
        report.results.append(result)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="BD2 screenshot method diagnostic")
    parser.add_argument("--template", required=True,
                        help="Template path (e.g. BrownDust-II/templates/public/主界面.png)")
    parser.add_argument("--roi", required=True,
                        help="ROI in base-res coords, comma-sep (e.g. 1720,20,120,70)")
    parser.add_argument("--base-res", default="1920,1080",
                        help="Base resolution (default 1920,1080)")
    parser.add_argument("--debug-dir", default="./debug/diagnostic",
                        help="Debug image output dir")
    parser.add_argument("--methods", default="",
                        help="Comma-sep method list (default: all 4)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    roi = tuple(int(x) for x in args.roi.split(","))
    base_res = tuple(int(x) for x in args.base_res.split(","))
    methods = [m.strip() for m in args.methods.split(",") if m.strip()] or None

    # Auto-discover BD2. Discovery may surface multiple windows whose title
    # contains "BrownDust" (e.g. an IDE tab previewing a debug image like
    # "match_fail_BrownDust-II_..._主界面.png_*.png - Trae CN"). Filter those
    # out: real game windows have class UnityWndClass and a short title
    # ("BrownDust II"), while editor/preview windows contain ".png", " - ",
    # "Trae", "VSCode", etc.
    from devices.center import DeviceCenter
    center = DeviceCenter()
    discovered = center.auto_discover()
    bd2 = None
    rejected_names = []
    for dev in discovered:
        if "windows" not in type(dev).__name__.lower():
            continue
        name = (getattr(dev, "name", "") or "").strip()
        lower = name.lower()
        # Skip editor/preview windows that happen to contain "browndust"
        # because they're previewing a debug image file.
        if any(skip in lower for skip in (".png", " - ", "trae", "vscode", "editor")):
            rejected_names.append(name)
            continue
        if "browndust" in lower:
            bd2 = dev
            break
    if bd2 is None:
        # Fallback: any WindowsDevice that wasn't rejected as an editor.
        for dev in discovered:
            if "windows" not in type(dev).__name__.lower():
                continue
            name = (getattr(dev, "name", "") or "").strip()
            lower = name.lower()
            if any(skip in lower for skip in (".png", " - ", "trae", "vscode", "editor")):
                continue
            bd2 = dev
            break
    if bd2 is None:
        print("[ERROR] No Windows device found. Is BD2 running?")
        if rejected_names:
            print(f"  (rejected editor/preview windows: {rejected_names})")
        return 1

    print(f"Using device: {bd2.device_id} ({bd2.name})")
    if hasattr(bd2, "connect"):
        bd2.connect()

    report = run_diagnostic(
        device=bd2,
        template_path=args.template,
        roi_base=roi,
        base_res=base_res,
        debug_dir=args.debug_dir,
        methods=methods,
    )

    print()
    print(report.summary_table())
    print()
    best = report.best_method()
    if best and best.template_match_success:
        print(f"✅ RECOMMENDED METHOD: {best.method} (confidence={best.template_match_confidence:.4f})")
        print(f"   Debug image: {best.debug_image_path}")
        return 0
    elif best:
        print(f"⚠️  BEST METHOD (but still below threshold): {best.method} "
              f"(confidence={best.template_match_confidence:.4f})")
        print(f"   Debug image: {best.debug_image_path}")
        print("   → Recommend: inspect debug image to check ROI/template alignment")
        return 1
    else:
        print("❌ ALL METHODS FAILED or returned blank frames")
        print("   → User intervention required: check BD2 window is visible / not minimized")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
