---
id: N133
date: 2026-06-23
symptom: Test script loops clicking all emulator icons; GAF click/input APIs only
  support Windows devices, not emulators
category: testing
cause: Test script used cv2.findContours to find ALL icons then clicked each one to
  check if Arknights launched; GAF DeviceClickView/DeviceInputView had no emulator
  code path
solution: '1. Stop the buggy find_arknights_click.py script (it iterates all contours
  and clicks each).
  2. Use OCR (RapidOCR) to identify the ''明日方舟'' text label (score=1.000), then click
  the icon ABOVE the text — not loop over every icon.
  3. Add ADB input tap support to DeviceClickView for emulator devices (device_type
  == EMULATOR).
  4. Add _execute_adb_action() to DeviceInputView for key_press/text_input/swipe/scroll
  on emulators.
  5. Extend emulator.py registry search to cover LDPlayer14 install paths (not just
  ldplayer9).
  6. Add DeviceTemplateMatchView (multi-scale cv2.matchTemplate) and DeviceColorDetectView
  (HSV range) endpoints.
  7. Add frontend template-match/color-detect tabs to DeviceOperationPanel.
  '
priority: high
diff_keywords: ["test", "script", "loops", "clicking", "all", "emulator", "icons", "gaf", "click", "input", "apis", "only"]
related_files:
- backend/workers/views.py
- backend/workers/urls.py
- frontend/src/api/devices.ts
- frontend/src/components/device/DeviceOperationPanel.tsx
cross_refs:
- N131
- N126
created_by: AI
level: L1
n_id: N133
topic: testing
---





# N133 — Emulator device control gap + test script loop bug

## What happened

The user reported the AI was "loop clicking all game icons at the bottom of the emulator" and asked if the device control code was broken.

Root cause analysis found TWO issues:

1. **Test script logic bug (NOT a GAF code issue)**: The `find_arknights_click.py` test script used `cv2.findContours` to detect ALL icons on the emulator home screen, then clicked each icon one by one to check if Arknights launched. This caused the visible loop-clicking behavior.

2. **GAF emulator support gap (real bug)**: `DeviceClickView` and `DeviceInputView` only had Windows code paths (Win32 API). Emulator devices (device_type == EMULATOR) fell through with no input method, so clicks/inputs silently failed on emulators.

## Fix

### Backend
- `DeviceClickView`: Added ADB `input tap` branch for emulator devices using `adb -s <serial> shell input tap <x> <y>`.
- `DeviceInputView`: Added `_execute_adb_action()` method dispatching to `adb shell input keyevent/text/swipe/scroll`.
- `emulator.py`: Extended registry search from `ldplayer9` only to `ldplayer9` + `ldplayer14` + `ldplayer` so LDPlayer14's adb.exe is found.
- `DeviceTemplateMatchView` (new): Multi-scale `cv2.matchTemplate` + `cv2.minMaxLoc`, accepts base64 template, returns score/location/center.
- `DeviceColorDetectView` (new): HSV range matching with `cv2.inRange` + moments, returns pixel_count/bbox/centroid.
- `urls.py`: Registered `template-match/` and `color-detect/` routes.

### Frontend
- `frontend/src/api/devices.ts`: Added `templateMatchDevice()` and `colorDetectDevice()` functions with typed params/results.
- `DeviceOperationPanel.tsx`: Added template-match tab (upload + threshold slider + match + click center) and color-detect tab (HSV lower/upper + preset colors + detect + click centroid). Fixed antd v5 deprecations (`Space direction` → `orientation`, `InputNumber addonBefore` → `Text` label).

## Verification

- OCR (RapidOCR) identified '明日方舟' text: score=1.000, box=[[1340,303],[1420,303],[1420,330],[1340,330]].
- GAF click API at (1379,256) → `mCurrentFocus=com.hypergryph.arknights` → game actually launched.
- template-match API: score=0.7245, scale=0.4, center=(1381,259) → click → game launched.
- color-detect API: red pixels=6404, blue pixels=131546 — both succeed.
- Playwright UI test: 8 tabs visible (点击/按键/文本/滑动/滚动/模板匹配/颜色匹配/历史), 0 console errors.

## Takeaways

1. **Test scripts must not loop-click all candidates.** When locating an app icon, use OCR to find the text label first, then click the icon ABOVE the text — not iterate every contour. Loop-clicking all icons is a UX disaster and wastes time.
2. **Device control APIs must cover ALL device types.** A click/input API that only handles Windows is half-implemented. Emulator devices need ADB `input` commands; the abstraction must dispatch by `device_type`.
3. **Registry search must cover all LDPlayer versions.** LDPlayer14 uses a different registry key (`SOFTWARE\leidian\ldplayer14`) than LDPlayer9. Hardcoding one version breaks adb discovery.
4. **Template match + color detect are first-class device operations.** They belong in the device operation panel alongside click/key/text/swipe/scroll, not hidden in a separate tool.
