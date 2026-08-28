---
date: 2026-07-05
symptom: [agent-platform, screenshot, gdi, printwindow, occluded-window, benchmark, dpi-awareness, game-window]
solution: GDI BitBlt cannot capture occluded windows — benchmark picks fastest method not most reliable. For game windows (UnityWndClass/UnrealWindow/etc.), always prefer PrintWindow. Apply DPI awareness at module load or GDI returns logical pixels (1024x576) instead of physical (1536x864).
diff_keywords: ["screenshot", "device", "benchmark", "dpi", "diagnostic", "screenshot_diagnostic", "template", "match", "template_match", "settings", "agent-platform", "gdi"]
related_files:
  - agent/src/platforms/windows/screenshot.py
  - agent/src/platforms/windows/device.py
  - agent/src/platforms/windows/benchmark.py
  - agent/src/platforms/windows/dpi.py
  - agent/src/utils/screenshot_diagnostic.py
  - agent/src/engine/nodes/template_match.py
  - resources/BrownDust II/config/settings.json
created_by: AI
priority: high
cross_refs: []
level: L1
n_id: N141
topic: debug-autoheal
---


# N141 — Screenshot Method Benchmark Blindspot + DPI Awareness + Occluded Game Windows

## Symptom (症状)

template_match confidence dropped to **0.2694** when BD2 game window was
occluded by IDE. The ROI blue box landed on the title bar instead of game
content. Diagnostic showed:

- WGC: 1024x576 (broken — E_NOINTERFACE)
- DXGI: 1024x576 (broken — Python int too large)
- GDI: 1024x576, conf=0.0779 (captured occluding window's pixels)
- PrintWindow: 1024x576, conf=0.2222 (captured game but DPI-virtualized)

After fixing DPI awareness, all captures became 1536x864 physical pixels:

- WGC: 1536x864, conf=0.1379 (still broken — E_NOINTERFACE)
- DXGI: 1536x864, conf=0.1379 (still broken — Python int too large)
- GDI: 1536x864, conf=0.1379 (captures occluding window's pixels)
- **PrintWindow: 1536x864, conf=0.9529** ✅

## Root Cause (根因)

Three independent bugs combined:

### Bug 1: benchmark.py only tests speed, not reliability
`benchmark_capture_methods(hwnd)` returns the fastest method. GDI wins
(13ms vs PrintWindow's 33ms) but GDI's BitBlt captures what's visible
on screen — when the game window is occluded, GDI captures the occluding
window's pixels. The benchmark never validates capture correctness.

### Bug 2: GDI/PrintWindow returned DPI-virtualized logical pixels
Python process was not DPI-aware. Without `SetProcessDpiAwareness` /
`SetProcessDPIAware`, GDI returns 1024x576 (logical) instead of 1536x864
(physical). coord_transformer computed scale_ratio = 1024/1920 = 0.5333
instead of the correct 1536/1920 = 0.8, breaking template scaling.

`dpi.py` exists with `apply_dpi_awareness()` but only triggers when
`display_builder.py` is imported. `screenshot.py` doesn't import
`display_builder`, so direct ScreenshotManager users (diagnostics, tests)
get DPI-virtualized captures.

### Bug 3: ScreenshotManager defaulted to client_only=False
`ScreenshotManager(client_only=False)` made GDI use `GetWindowDC` +
`GetWindowRect`, capturing the full window including title bar (1558x920).
But coord_transformer works in client-physical coords (1536x864). The 22px
horizontal / 56px vertical offset is the chrome, causing the ROI blue box
to land on the title bar.

## Fix (修复)

Commit `-` fixed all three bugs:

### Fix 1: Game window heuristic in _detect_best_method
```python
# screenshot.py
_GAME_WINDOW_CLASSES = frozenset({
    "UnityWndClass", "UnrealWindow", "LaunchUnrealUWindowsClient",
    "Godot_Engine_Wnd", "FFXIVGAME", "ArenaNet_Dx_Window_Class",
    "CrypticWindow",
})

def _detect_best_method(self):
    # 1. Game window heuristic — prefer PrintWindow unconditionally.
    if self._hwnd and self._is_game_window():
        return self.PRINTWINDOW
    # 2. Run benchmark for non-game windows.
    ...
```

### Fix 2: Apply DPI awareness at screenshot.py module load
```python
# screenshot.py — top of file
from platforms.windows import dpi  # noqa: F401  — triggers apply_dpi_awareness()
```

### Fix 3: client_only=True for WindowsDevice
```python
# device.py
self._screenshot_mgr = ScreenshotManager(method=screenshot_method, client_only=True)
```

### Fix 4: GDI _capture_gdi() branches on client_only
```python
if self._client_only and self._hwnd:
    # GetDC + GetClientRect — client area only
    src_dc = user32.GetDC(self._hwnd)
else:
    # GetWindowDC + GetWindowRect — full window with chrome
    src_dc = user32.GetWindowDC(hwnd)
```

### Fix 5: Explicit per-game config
```json
// BrownDust-II/config/settings.json
"screenshot_method_preference": "printwindow"  // was "auto"
```

## Prevention (预防)

- **Game windows = always PrintWindow**: GDI BitBlt cannot capture occluded
  content. Any window with class UnityWndClass/UnrealWindow/Godot_*/etc.
  must use PrintWindow (PW_CLIENTONLY + PW_RENDERFULLCONTENT).
- **Apply DPI awareness at module load**: any module that calls GDI/PrintWindow
  must import `platforms.windows.dpi` at the top. Don't rely on caller
  behavior.
- **client_only=True is the default for game automation**: coord_transformer
  works in client-physical coords, so screenshots must also be client-only.
  Title bar/borders add chrome offset that breaks ROI alignment.
- **Benchmark must validate reliability, not just speed**: TD-006 ✅ FIXED.
  `benchmark_capture_methods` now compares each method's capture to PrintWindow
  (ground truth) via normalized MAD; methods with reliability < 0.95 are
  demoted to the back of the speed ranking. Verified on real BD2 window:
  GDI reliability=0.7921 (unreliable, occluded) vs PrintWindow reliability=0.9979.
- **Diagnostic-first debugging**: when template_match fails, run
  `utils.screenshot_diagnostic.run_diagnostic()` before guessing. It
  iterates all 4 methods and reports confidence for each.

## AI Auto-Heal Integration (TD-007, commit -)

When `debug_mode=True` and template_match fails, `_auto_heal_and_retry()`
in `template_match.py` automatically:
1. Calls `screenshot_diagnostic.run_diagnostic()` to test all methods
2. If best method's confidence ≥ threshold, switches device's screenshot
   method via `ScreenshotManager.set_method()` and re-runs the match
3. If all methods fail, returns fail_result with full diagnostic report

End-to-end test: force GDI → auto-heal switches to PrintWindow → match
succeeds with conf=0.9529.

## Evidence (3 步)

- **Problem**: template_match confidence=0.2694 on BD2 main screen.
  Screenshot was 1558x920 (window rect with chrome), coord_transformer
  expected 1536x864 (client rect). ROI blue box landed on title bar.
- **Solution**: commit `-` (5 fixes above) + commit `-`
  (auto-heal integration). PrintWindow confidence=0.9529 verified on
  real BD2 window (hwnd=2951474, class=UnityWndClass) occluded by Trae CN IDE.
- **Verification**: `临时验证脚本 (已删除)` — force GDI → auto-heal
  switches to PrintWindow → match succeeds conf=0.9529, center=(945, 31).

## Related

- TD-001 (WGC broken — E_NOINTERFACE) — not blocking, PrintWindow works
- TD-002 (DXGI broken — Python int too large) — not blocking
- TD-003 (GDI occluded window bug) — ✅ FIXED, this lesson
- TD-006 (benchmark only tests speed) — ✅ FIXED, reliability dimension added
- TD-007 (auto-heal not integrated) — ✅ FIXED, this lesson
- N138 (ctypes HRESULT signed comparison) — related to TD-002 DXGI bug
