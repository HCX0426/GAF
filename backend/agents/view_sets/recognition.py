import logging

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission
from agents.models import Device
from agents.view_sets.capture import _capture_device_screenshot

logger = logging.getLogger(__name__)


# Import service-layer helpers (moved to agents/services/device_service.py in Phase 1).


class DeviceTemplateMatchView(APIView):
    """Device template matching endpoint
    POST /api/v2/devices/{id}/template-match/

    Captures a screenshot from the device and runs cv2.matchTemplate
    to find the template image. Returns the best match location and score.

    Request body (JSON):
    {
        "template_base64": str,   // Base64-encoded template image (required)
        "threshold": float,       // Min match score 0-1 (default 0.5)
        "scales": [float],        // Scales to try (default [0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0])
        "method": str             // cv2 method name (default TM_CCOEFF_NORMED)
    }

    Response:
    {
        "success": bool,
        "matched": bool,
        "score": float,
        "x": int,                 // Top-left X of best match
        "y": int,                 // Top-left Y of best match
        "width": int,             // Template width at best scale
        "height": int,            // Template height at best scale
        "center_x": int,          // Center X
        "center_y": int,          // Center Y
        "scale": float,           // Best scale
        "error": str | null
    }
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        description="Run cv2.matchTemplate on a captured screenshot to find a template image.",
    )
    def post(self, request: Request, id: int):
        try:
            device = Device.objects.select_related("agent").get(pk=id)
        except Device.DoesNotExist:
            return Response(
                {"success": False, "error": f"Device {id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if device.status not in [device.Status.ONLINE, device.Status.BUSY]:
            return Response(
                {"success": False, "error": f"Device {device.name} is not online"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        template_b64 = request.data.get("template_base64")
        if not template_b64:
            return Response(
                {"success": False, "error": "Missing required field: template_base64"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        threshold = float(request.data.get("threshold", 0.5))
        scales = request.data.get("scales", [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        method_name = request.data.get("method", "TM_CCOEFF_NORMED")

        try:
            import base64

            import cv2
            import numpy as np

            # Decode template
            template_bytes = base64.b64decode(template_b64)
            template_arr = np.frombuffer(template_bytes, np.uint8)
            template = cv2.imdecode(template_arr, cv2.IMREAD_COLOR)
            if template is None:
                return Response(
                    {"success": False, "error": "Failed to decode template image"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Capture screenshot (TD-257 修复: call module-level function)
            screenshot_bytes = _capture_device_screenshot(device)
            if not screenshot_bytes:
                return Response(
                    {"success": False, "error": "Failed to capture screenshot"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            screenshot_arr = np.frombuffer(screenshot_bytes, np.uint8)
            screenshot = cv2.imdecode(screenshot_arr, cv2.IMREAD_COLOR)
            if screenshot is None:
                return Response(
                    {"success": False, "error": "Failed to decode screenshot"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Get cv2 method
            cv2_methods = {
                "TM_CCOEFF_NORMED": cv2.TM_CCOEFF_NORMED,
                "TM_CCORR_NORMED": cv2.TM_CCORR_NORMED,
                "TM_SQDIFF_NORMED": cv2.TM_SQDIFF_NORMED,
            }
            method = cv2_methods.get(method_name, cv2.TM_CCOEFF_NORMED)

            # Multi-scale template matching
            best_score: float = -1.0
            best_loc: tuple[int, int] = (0, 0)
            best_scale = 1.0
            best_size = (0, 0)

            for scale in scales:
                new_w = int(template.shape[1] * scale)
                new_h = int(template.shape[0] * scale)
                if new_w < 10 or new_h < 10 or new_w > screenshot.shape[1] or new_h > screenshot.shape[0]:
                    continue
                scaled = cv2.resize(template, (new_w, new_h))
                result = cv2.matchTemplate(screenshot, scaled, method)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

                # For SQDIFF, lower is better
                if method == cv2.TM_SQDIFF_NORMED:
                    score = 1 - min_val
                    loc = min_loc
                else:
                    score = max_val
                    loc = max_loc

                if score > best_score:
                    best_score = score
                    best_loc = (loc[0], loc[1])
                    best_scale = scale
                    best_size = (new_w, new_h)

            x, y = best_loc
            w, h = best_size
            matched = best_score >= threshold

            logger.info(
                "Template match for device %s: score=%.4f matched=%s loc=(%d,%d) scale=%.2f",
                device.name,
                best_score,
                matched,
                x,
                y,
                best_scale,
            )

            # For Windows devices, convert screenshot coordinates to client coordinates
            # This handles DPI scaling (screenshot may be physical pixels, client area is logical)
            # B001 fix: delegate to agent.platforms.windows.window_info.
            client_scale = 1.0
            if device.device_type == Device.DeviceType.WINDOWS and device.window_handle:
                from device_bridge.platforms.windows.window_info import get_client_scale

                try:
                    hwnd = int(device.window_handle, 0) if device.window_handle else 0
                    if hwnd and screenshot.shape[1] > 0:
                        client_scale = get_client_scale(hwnd, screenshot.shape[1])
                except Exception as e:
                    logger.warning(
                        "get_client_scale failed for device %s: %s",
                        device.id,
                        e,
                    )

            # Center coordinates in client logical space (for click API)
            client_cx = int((x + w // 2) * client_scale)
            client_cy = int((y + h // 2) * client_scale)

            return Response(
                {
                    "success": True,
                    "matched": matched,
                    "score": round(float(best_score), 4),
                    "x": int(x),
                    "y": int(y),
                    "width": int(w),
                    "height": int(h),
                    "center_x": int(x + w // 2),
                    "center_y": int(y + h // 2),
                    "center_x_client": client_cx,
                    "center_y_client": client_cy,
                    "client_scale": round(client_scale, 4),
                    "scale": float(best_scale),
                    "error": None,
                }
            )

        except Exception as e:
            logger.error("Template match failed for device %d: %s", id, e, exc_info=True)
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DeviceColorDetectView(APIView):
    """Device color detection endpoint
    POST /api/v2/devices/{id}/color-detect/

    Captures a screenshot and detects pixels within the given HSV color range.
    Returns the bounding box and centroid of matched pixels.

    Request body (JSON):
    {
        "lower_hsv": [h, s, v],    // Lower HSV bound (required, 0-180/0-255/0-255)
        "upper_hsv": [h, s, v],    // Upper HSV bound (required)
        "min_pixels": int,         // Min pixel count to report match (default 100)
        "region": [x, y, w, h]     // Optional ROI to restrict detection
    }

    Response:
    {
        "success": bool,
        "matched": bool,
        "pixel_count": int,
        "bbox": [x, y, w, h],      // Bounding box of matched pixels
        "centroid": [cx, cy],      // Centroid of matched pixels
        "error": str | null
    }
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        description="Detect pixels within an HSV color range on a captured screenshot.",
    )
    def post(self, request: Request, id: int):
        try:
            device = Device.objects.select_related("agent").get(pk=id)
        except Device.DoesNotExist:
            return Response(
                {"success": False, "error": f"Device {id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if device.status not in [device.Status.ONLINE, device.Status.BUSY]:
            return Response(
                {"success": False, "error": f"Device {device.name} is not online"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lower_hsv = request.data.get("lower_hsv")
        upper_hsv = request.data.get("upper_hsv")
        if not lower_hsv or not upper_hsv:
            return Response(
                {"success": False, "error": "Missing required fields: lower_hsv, upper_hsv"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        min_pixels = int(request.data.get("min_pixels", 100))
        region = request.data.get("region")

        try:
            import cv2
            import numpy as np

            # Capture screenshot (TD-257 修复: call module-level function)
            screenshot_bytes = _capture_device_screenshot(device)
            if not screenshot_bytes:
                return Response(
                    {"success": False, "error": "Failed to capture screenshot"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            arr = np.frombuffer(screenshot_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return Response(
                    {"success": False, "error": "Failed to decode screenshot"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Apply ROI if specified
            if region and len(region) == 4:
                rx, ry, rw, rh = region
                img = img[int(ry) : int(ry + rh), int(rx) : int(rx + rw)]
                offset_x, offset_y = int(rx), int(ry)
            else:
                offset_x, offset_y = 0, 0

            # Convert to HSV and apply color range
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            lower = np.array(lower_hsv, dtype=np.uint8)
            upper = np.array(upper_hsv, dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)

            # Find non-zero pixels
            ys, xs = np.nonzero(mask)
            pixel_count = len(ys)

            if pixel_count < min_pixels:
                return Response(
                    {
                        "success": True,
                        "matched": False,
                        "pixel_count": int(pixel_count),
                        "bbox": None,
                        "centroid": None,
                        "error": None,
                    }
                )

            # Compute bbox and centroid
            x_min, x_max = int(xs.min()), int(xs.max())
            y_min, y_max = int(ys.min()), int(ys.max())
            cx = int(xs.mean()) + offset_x
            cy = int(ys.mean()) + offset_y

            logger.info(
                "Color detect for device %s: pixels=%d bbox=(%d,%d,%d,%d) centroid=(%d,%d)",
                device.name,
                pixel_count,
                x_min + offset_x,
                y_min + offset_y,
                x_max - x_min + 1,
                y_max - y_min + 1,
                cx,
                cy,
            )

            return Response(
                {
                    "success": True,
                    "matched": True,
                    "pixel_count": int(pixel_count),
                    "bbox": [x_min + offset_x, y_min + offset_y, x_max - x_min + 1, y_max - y_min + 1],
                    "centroid": [cx, cy],
                    "error": None,
                }
            )

        except Exception as e:
            logger.error("Color detect failed for device %d: %s", id, e, exc_info=True)
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
