"""E2E verification for I1 fix (task.result WS protocol handler).

Verifies that the WebSocket channel through which ``task.result`` messages
flow is healthy, and that the device-center UI (which would surface task
results) renders without JS errors.

The I1 fix lives in ``backend/protocol/consumers.py`` (WorkerConsumer):
  - handler_map includes ``MessageType.TASK_RESULT: self._handle_task_result``
  - ``_handle_task_result`` persists the result via ``_db_update_execution_result``
    (success flag + error_msg + elapsed_time) and releases concurrency/device state

This script does NOT trigger a real task (no device is attached). Instead it:
  1. Confirms the I1 handler is registered in protocol/consumers.py (static check)
  2. Logs in via the browser
  3. Opens the device center page and verifies it renders
  4. Hooks ``window.WebSocket`` before page load to observe the WS lifecycle
  5. Verifies the frontend wsClient establishes a WS connection to the backend
     and receives the ``client.connected`` handshake message
  6. Records console errors / page JS exceptions
  7. Saves a screenshot to ``.trash/e2e_screenshot.png``

Usage:
    conda run -n gaf python scripts/e2e/scenarios/verify_task_result_e2e.py

If Playwright is missing:
    conda run -n gaf pip install playwright
    conda run -n gaf playwright install chromium
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONSUMERS_PATH = REPO_ROOT / "backend" / "protocol" / "consumers.py"
SCREENSHOT_PATH = REPO_ROOT / ".trash" / "e2e_screenshot.png"

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173")
USERNAME = "admin"
PASSWORD = "admin123"

# Injected before any page script. Wraps the native WebSocket constructor so
# we can observe every WS instance the frontend creates, its readyState
# transitions, and every inbound message. Stored on window.__gaf_ws_probe.
#
# NOTE: add_init_script evaluates raw JS — must be an IIFE, not a bare arrow
# function expression (which would just create and discard a function).
WS_PROBE_INIT_SCRIPT = r"""
(() => {
  if (window.__gaf_ws_probe_installed) return;
  window.__gaf_ws_probe_installed = true;
  window.__gaf_ws_probe = {
    instances: [],
    messages: [],
    errors: [],
  };
  const NativeWS = window.WebSocket;
  function ProbeWS(url, protocols) {
    const ws = protocols ? new NativeWS(url, protocols) : new NativeWS(url);
    const entry = {
      url: url,
      readyState: ws.readyState,
      opened: false,
      closed: false,
      protocol: '',
    };
    window.__gaf_ws_probe.instances.push(entry);
    ws.addEventListener('open', () => {
      entry.opened = true;
      entry.readyState = ws.readyState;
      entry.protocol = ws.protocol || '';
    });
    ws.addEventListener('message', (ev) => {
      let parsed = null;
      try { parsed = JSON.parse(ev.data); } catch (_) { parsed = null; }
      window.__gaf_ws_probe.messages.push({
        url: url,
        raw: typeof ev.data === 'string' ? ev.data.slice(0, 500) : '[non-string]',
        type: parsed && parsed.type ? parsed.type : null,
        ts: Date.now(),
      });
    });
    ws.addEventListener('close', () => {
      entry.closed = true;
      entry.readyState = ws.readyState;
    });
    ws.addEventListener('error', () => {
      window.__gaf_ws_probe.errors.push({ url: url, ts: Date.now() });
    });
    return ws;
  }
  ProbeWS.CONNECTING = NativeWS.CONNECTING;
  ProbeWS.OPEN = NativeWS.OPEN;
  ProbeWS.CLOSING = NativeWS.CLOSING;
  ProbeWS.CLOSED = NativeWS.CLOSED;
  ProbeWS.prototype = NativeWS.prototype;
  window.WebSocket = ProbeWS;
})();
"""


def _check_i1_handler_registered() -> tuple[bool, str]:
    """Static check: confirm ``task.result`` handler is wired in protocol/consumers.py."""
    if not CONSUMERS_PATH.exists():
        return False, f"consumers.py not found at {CONSUMERS_PATH}"
    src = CONSUMERS_PATH.read_text(encoding="utf-8")
    has_mapping = "MessageType.TASK_RESULT: self._handle_task_result" in src
    has_handler = "async def _handle_task_result(self, frame):" in src
    has_persist = "await self._db_update_execution_result(" in src
    if has_mapping and has_handler and has_persist:
        return True, "task.result handler registered + persists execution result"
    missing = []
    if not has_mapping:
        missing.append("handler_map entry missing")
    if not has_handler:
        missing.append("_handle_task_result method missing")
    if not has_persist:
        missing.append("result persist (_db_update_execution_result) missing")
    return False, "; ".join(missing)


def _format_table(rows: list[tuple[str, str]]) -> str:
    """Render a two-column (Check, Result) table."""
    header = f"{'Check':<48} | {'Result':<10}"
    sep = "-" * 48 + "-+-" + "-" * 10
    lines = [header, sep]
    for name, result in rows:
        lines.append(f"{name:<48} | {result:<10}")
    return "\n".join(lines)


def main() -> int:
    # Try to import Playwright up front so we can emit a helpful install hint.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] Playwright is not installed in the gaf conda env.")
        print("        Install it with:")
        print("        conda run -n gaf pip install playwright")
        print("        conda run -n gaf playwright install chromium")
        return 3

    SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, str]] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    final_probe: dict | None = None

    # Static check first (does not require the browser).
    i1_ok, i1_detail = _check_i1_handler_registered()
    results.append(("I1 handler registered in protocol/consumers.py", "PASS" if i1_ok else "FAIL"))
    print(f"[STATIC] I1 handler check: {i1_detail}")

    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                channel="chrome",
                args=["--start-maximized", "--window-position=0,0"],
            )
            context = browser.new_context(
                no_viewport=True,
                locale="zh-CN",
            )
            # Inject WS probe BEFORE any page script so we catch the wsClient
            # connection made by WebSocketProvider immediately after login.
            context.add_init_script(WS_PROBE_INIT_SCRIPT)
            page = context.new_page()

            # Console + page-error listeners
            def _on_console(msg):
                if msg.type == "error":
                    console_errors.append(f"[console.error] {msg.text}")

            def _on_page_error(exc):
                page_errors.append(f"[pageerror] {exc}")

            page.on("console", _on_console)
            page.on("pageerror", _on_page_error)

            # --- Step 1: navigate to login page ---
            print("[STEP] navigating to login page")
            page.goto(f"{FRONTEND_URL}/login", wait_until="networkidle", timeout=20000)
            login_page_loaded = "login" in page.url.lower() or "/login" in page.url
            results.append(("Login page loaded", "PASS" if login_page_loaded else "FAIL"))

            # --- Step 2: fill credentials and submit ---
            print("[STEP] filling credentials and submitting")
            page.locator('input[autocomplete="username"]').fill(USERNAME)
            page.locator('input[autocomplete="current-password"]').fill(PASSWORD)
            page.locator('button[type="submit"]').click()

            # --- Step 3: verify login success (URL -> /dashboard) ---
            try:
                page.wait_for_url("**/dashboard**", timeout=15000)
                login_ok = True
            except Exception:
                # Fall back to checking that we left /login
                login_ok = "/login" not in page.url
            results.append(("Login success (URL -> /dashboard)", "PASS" if login_ok else "FAIL"))
            print(f"[STEP] login result: {'OK' if login_ok else 'FAIL'} url={page.url}")

            if not login_ok:
                # Save a screenshot for diagnosis even on failure.
                page.screenshot(path=str(SCREENSHOT_PATH), full_page=True)
                results.append(("Device center page rendered", "SKIP"))
                results.append(("WS connection established (wsClient -> /ws/dashboard/)", "SKIP"))
                results.append(("WS received backend message on /ws/dashboard/", "SKIP"))
                results.append(("Screenshot saved to .trash/e2e_screenshot.png",
                                "PASS" if SCREENSHOT_PATH.exists() else "FAIL"))
                results.append(("No JS console errors", "FAIL" if console_errors else "PASS"))
                results.append(("No JS page exceptions", "FAIL" if page_errors else "PASS"))
                print("\n" + _format_table(results))
                print(f"\nconsole_errors={len(console_errors)} page_errors={len(page_errors)}")
                return 1

            # --- Step 4: verify WS connectivity on /dashboard first ---
            # The WebSocketProvider calls wsClient.connect() right after auth
            # succeeds. The probe (installed via add_init_script) captures the
            # WebSocket instance + inbound messages. We check here while still
            # on /dashboard so a subsequent full navigation can't wipe the
            # captured state before we read it.
            #
            # We filter to the /ws/dashboard/ endpoint specifically (the Vite
            # HMR socket at the root URL and the notifications socket also
            # appear in the probe). The dashboard socket only carries backend
            # ClientConsumer pushes — Vite HMR lives on a different URL — so
            # ANY message received on it proves the backend -> frontend WS
            # path is bidirectional. That is the same channel task.result
            # messages (I1 fix) will travel through.
            print("[STEP] waiting for WS connection + backend message (on /dashboard)")
            ws_connected = False
            got_backend_msg = False
            dashboard_msg_types: list[str] = []
            deadline = time.time() + 15
            while time.time() < deadline:
                probe = page.evaluate(
                    "() => { const p = window.__gaf_ws_probe || {instances:[],messages:[],errors:[]};"
                    " const dashMsgs = p.messages.filter(m => (m.url||'').includes('/ws/dashboard/'));"
                    " return {"
                    "  instance_count: p.instances.length,"
                    "  any_open: p.instances.some(i => i.opened),"
                    "  any_dashboard: p.instances.some(i => (i.url||'').includes('/ws/dashboard/')),"
                    "  dash_msg_types: dashMsgs.map(m => m.type),"
                    "  errors: p.errors.length"
                    "}; }"
                )
                if probe.get("any_open") and probe.get("any_dashboard"):
                    ws_connected = True
                dashboard_msg_types = probe.get("dash_msg_types") or []
                # Any message on the dashboard socket is a backend push
                # (client.connected handshake, agent_heartbeat, device.updated,
                # task.status_update, etc.). Vite HMR is on a different URL.
                if dashboard_msg_types:
                    got_backend_msg = True
                if ws_connected and got_backend_msg:
                    break
                page.wait_for_timeout(500)

            results.append(("WS connection established (wsClient -> /ws/dashboard/)",
                            "PASS" if ws_connected else "FAIL"))
            results.append(("WS received backend message on /ws/dashboard/",
                            "PASS" if got_backend_msg else "FAIL"))
            print(f"[STEP] WS connected={ws_connected} backend_msg={got_backend_msg} "
                  f"types={dashboard_msg_types}")

            # --- Step 5: navigate to device center (/devices) ---
            print("[STEP] navigating to /devices")
            try:
                page.goto(f"{FRONTEND_URL}/devices", wait_until="domcontentloaded", timeout=20000)
            except Exception as exc:
                print(f"[WARN] /devices navigation timeout: {exc}")

            # Wait for the device center page to actually render. The page uses
            # PageWrapper + antd layout; look for any heading / button / card.
            page_rendered = False
            try:
                # DeviceCenterPage renders a Typography.Title (h1/h2/h3) plus
                # action buttons (Scan / Reload / Add). Wait for any of them.
                page.locator('h1, h2, h3, .ant-typography, button').first.wait_for(
                    state="visible", timeout=10000
                )
                page_rendered = True
            except Exception:
                # Fall back to body content presence
                try:
                    body_text = page.locator("body").inner_text(timeout=3000)
                    page_rendered = len(body_text.strip()) > 50
                except Exception:
                    page_rendered = False
            results.append(("Device center page rendered", "PASS" if page_rendered else "FAIL"))
            print(f"[STEP] /devices rendered: {page_rendered}")

            # Final probe snapshot for the report (captured on /devices after
            # reconnection; falls back to the dashboard probe state if the
            # /devices probe hasn't recorded anything yet).
            final_probe = page.evaluate(
                "() => { const p = window.__gaf_ws_probe || {instances:[],messages:[],errors:[]};"
                " const dashMsgs = p.messages.filter(m => (m.url||'').includes('/ws/dashboard/'));"
                " return {"
                "  instances: p.instances.map(i => ({url:i.url, opened:i.opened, closed:i.closed})),"
                "  dash_msg_count: dashMsgs.length,"
                "  dash_msg_types: dashMsgs.map(m => m.type),"
                "  total_msg_count: p.messages.length,"
                "  errors: p.errors"
                "}; }"
            )

            # --- Step 6: screenshot ---
            try:
                page.screenshot(path=str(SCREENSHOT_PATH), full_page=True)
                screenshot_ok = SCREENSHOT_PATH.exists()
            except Exception as exc:
                print(f"[WARN] screenshot failed: {exc}")
                screenshot_ok = False
            results.append(("Screenshot saved to .trash/e2e_screenshot.png",
                            "PASS" if screenshot_ok else "FAIL"))

            # --- Step 7: JS error summary ---
            results.append(("No JS console errors",
                            "PASS" if not console_errors else f"FAIL({len(console_errors)})"))
            results.append(("No JS page exceptions",
                            "PASS" if not page_errors else f"FAIL({len(page_errors)})"))

            browser.close()
            browser = None
    except Exception as exc:
        print(f"[ERROR] browser automation failed: {exc}")
        results.append(("Browser automation", f"FAIL: {exc}"))
        return 2
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

    # --- Final report ---
    print("\n" + "=" * 70)
    print("I1 fix E2E verification — task.result WS protocol")
    print("=" * 70)
    print(_format_table(results))
    print("-" * 70)
    print(f"JS console errors: {len(console_errors)}")
    print(f"JS page exceptions: {len(page_errors)}")
    if final_probe:
        print(f"WS instances: {final_probe.get('instances')}")
        print(f"WS /ws/dashboard/ messages: {final_probe.get('dash_msg_count')} "
              f"(types: {final_probe.get('dash_msg_types')})")
        print(f"WS total messages (all endpoints): {final_probe.get('total_msg_count')}")
    if console_errors:
        print("\nConsole errors (first 5):")
        for line in console_errors[:5]:
            print(f"  {line}")
    if page_errors:
        print("\nPage exceptions (first 5):")
        for line in page_errors[:5]:
            print(f"  {line}")

    # Exit non-zero if any check failed.
    failed = [r for r in results if r[1].startswith("FAIL")]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
