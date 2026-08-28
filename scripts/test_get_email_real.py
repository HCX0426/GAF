"""Real-device smoke test: run BrownDust-II get_email pipeline against
the live game window.

Usage (from GAF root):
    conda run -n gaf python scripts/test_get_email_real.py

Verifies:
1. DeviceCenter.auto_discover() finds the BD2 game window
2. TaskOrchestrator.execute_pipeline() runs the pipeline end-to-end
3. Structured JSONL log is produced with normalization fields
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

# Ensure agent/src is importable
GAF_ROOT = Path(__file__).resolve().parent.parent
AGENT_SRC = GAF_ROOT / "agent" / "src"
if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

# Import engine.nodes to populate PIPELINE_NODE_REGISTRY before engine.load.
import engine.nodes  # noqa: F401
from core.config import AgentConfig
from core.orchestrator import TaskOrchestrator
from devices.center import DeviceCenter
from devices.manager import DeviceManager
from image.processor import ImageProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_get_email_real")


PIPELINE_PATH = GAF_ROOT / "resources" / "BrownDust-II" / "tasks" / "get_email.json"
DEBUG_DIR = GAF_ROOT / "debug" / "agent"


def main() -> int:
    # ── 1. Load pipeline JSON ───────────────────────────────────────
    if not PIPELINE_PATH.is_file():
        logger.error("Pipeline not found: %s", PIPELINE_PATH)
        return 2
    pipeline_json = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    logger.info("Loaded pipeline: %s (nodes=%d)",
                pipeline_json.get("name"), len(pipeline_json.get("nodes", [])))

    # ── 2. Discover devices ─────────────────────────────────────────
    center = DeviceCenter()
    devices = center.auto_discover()
    if not devices:
        logger.error("No devices discovered. Is the BD2 game window open?")
        return 3

    logger.info("Discovered %d device(s):", len(devices))
    for d in devices:
        info = {
            "device_id": d.device_id,
            "name": d.name,
            "type": type(d).__name__,
        }
        logger.info("  - %s", info)

    # Pick the first device (prefer Windows game window over ADB)
    target_device = devices[0]
    for d in devices:
        if type(d).__name__ == "WindowsDevice":
            target_device = d
            break
    logger.info("Selected device: %s (%s)",
                target_device.device_id, type(target_device).__name__)

    # ── 2b. Connect device ─────────────────────────────────────────
    # WindowsDevice starts in DISCONNECTED state; capture_screen/click
    # would be rejected by @require_operable. Explicitly connect first.
    try:
        target_device.connect()
        logger.info("Device connected: id=%s status=%s",
                    target_device.device_id, target_device.status)
    except Exception as exc:
        logger.error("Device connect failed: %s", exc, exc_info=True)
        return 4

    # ── 3. Build orchestrator ───────────────────────────────────────
    device_manager = DeviceManager()
    device_manager.add_device(target_device)
    image_processor = ImageProcessor()
    config = AgentConfig(
        is_local=True,
        debug_mode=True,
        debug_dir=str(DEBUG_DIR),
    )
    orchestrator = TaskOrchestrator(
        device_manager=device_manager,
        image_processor=image_processor,
        config=config,
    )

    # ── 4. Execute pipeline ─────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Starting pipeline execution...")
    logger.info("=" * 60)

    result = orchestrator.execute_pipeline(
        pipeline_json=pipeline_json,
        debug_mode=True,
        debug_dir=str(DEBUG_DIR),
        device_id=target_device.device_id,
    )

    logger.info("=" * 60)
    logger.info("Pipeline result:")
    logger.info("  success   = %s", result.success)
    logger.info("  elapsed   = %.3fs", result.elapsed_time)
    logger.info("  error_msg= %s", result.error_msg)
    if result.data is not None:
        if isinstance(result.data, dict):
            logger.info("  data keys = %s", list(result.data.keys())[:10])
        elif isinstance(result.data, list):
            logger.info("  data list (len=%d), first=%s",
                        len(result.data),
                        result.data[0] if result.data else None)
        else:
            logger.info("  data type = %s", type(result.data).__name__)
    logger.info("=" * 60)

    # ── 5. Locate the structured JSONL log ───────────────────────────
    # Debug artifacts are stored under <DEBUG_DIR>/<YYYY-MM-DD>/<pipeline_name>/<HHMMSS>_<exec_id>/structured/
    # Find the most recently modified exec-* directory under today's date.
    today_str = time.strftime("%Y-%m-%d")
    today_dir = DEBUG_DIR / today_str
    pipeline_name = pipeline_json.get("name", "pipeline")
    pipeline_dir = today_dir / pipeline_name

    exec_dirs: list[Path] = []
    if pipeline_dir.is_dir():
        exec_dirs = [p for p in pipeline_dir.iterdir() if p.is_dir() and p.name.split("_")[-1].startswith("exec-")]
    # Fallback: search whole DEBUG_DIR for any exec-* directory
    if not exec_dirs:
        exec_dirs = list(DEBUG_DIR.rglob("exec-*"))
        exec_dirs = [p for p in exec_dirs if p.is_dir()]

    if not exec_dirs:
        logger.warning("No exec-* directories found under %s", DEBUG_DIR)
    else:
        # Pick the latest by mtime
        latest_exec = max(exec_dirs, key=lambda p: p.stat().st_mtime)
        logger.info("Latest execution dir: %s", latest_exec)

        structured_dir = latest_exec / "structured"
        if structured_dir.is_dir():
            # JSONL file
            jsonl_files = sorted(structured_dir.glob("*.jsonl"),
                                 key=lambda p: p.stat().st_mtime,
                                 reverse=True)
            if jsonl_files:
                latest_jsonl = jsonl_files[0]
                logger.info("Latest JSONL: %s", latest_jsonl)
                try:
                    entries = []
                    with open(latest_jsonl, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                entries.append(json.loads(line))
                    logger.info("  entries = %d", len(entries))
                    for i, e in enumerate(entries):
                        node_id = e.get("node_id", "?")
                        node_type = e.get("node_type", "?")
                        success = e.get("success")
                        elapsed_ms = e.get("elapsed_ms", 0)
                        norm_keys = [k for k in (
                            "confidence", "roi_base", "roi_physical",
                            "scale_ratio", "screen_size", "template_name",
                        ) if k in e]
                        error_msg = e.get("error_msg", "")
                        if error_msg:
                            logger.info(
                                "  [%d] %s (%s) success=%s elapsed=%.1fms norm=%s err=%s",
                                i, node_id, node_type, success, elapsed_ms,
                                norm_keys, error_msg[:80],
                            )
                        else:
                            logger.info(
                                "  [%d] %s (%s) success=%s elapsed=%.1fms norm=%s",
                                i, node_id, node_type, success, elapsed_ms,
                                norm_keys,
                            )
                except Exception as exc:
                    logger.warning("Failed to read JSONL: %s", exc)

            # Diagnosis report
            diag_files = sorted(structured_dir.glob("*diagnosis*.md"),
                                key=lambda p: p.stat().st_mtime,
                                reverse=True)
            if diag_files:
                logger.info("Latest diagnosis: %s", diag_files[0])

            # Timeline
            tl_files = sorted(structured_dir.glob("*timeline*.md"),
                              key=lambda p: p.stat().st_mtime,
                              reverse=True)
            if tl_files:
                logger.info("Latest timeline: %s", tl_files[0])

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
