"""Background console monitor: keep Chrome open, log all console events.

Reusable interactive debugging tool. Launches a headed Chrome window, logs in,
then records all console messages (error/warning/info), page navigations,
failed network requests, page errors, and click targets to a log file.

Usage:
    conda run -n gaf python scripts/e2e/scenarios/console_monitor.py

User closes the Chrome window to stop monitoring. Then read the log file for
a summary.

Log file location: .trash/console_monitor.log (gitignored temp output).
"""
import os
import sys
import threading
import time
from pathlib import Path
from threading import Lock

from playwright.sync_api import sync_playwright

_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
LOGIN_URL = f"{_FRONTEND_URL}/login"
# Log output goes to .trash/ (gitignored temp dir) — the log is per-run
# scratch output, not a reusable artifact.
LOG_FILE = Path(__file__).resolve().parents[3] / ".trash" / "console_monitor.log"

_log_lock = Lock()
_log_file = open(LOG_FILE, "w", encoding="utf-8")
_start_ts = time.strftime("%Y-%m-%d %H:%M:%S")
_log_file.write(f"==== Console monitor started at {_start_ts} ====\n")
_log_file.flush()


def _write(line: str) -> None:
    ts = time.strftime("%H:%M:%S")
    with _log_lock:
        _log_file.write(f"[{ts}] {line}\n")
        _log_file.flush()


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            # no_viewport=True lets the browser window size drive the viewport
            # (equivalent to --start-maximized actually filling the window).
            # Without this, Playwright defaults to a 1280x720 viewport and
            # the app renders in the top-left corner of a maximized window.
            args=["--start-maximized", "--window-position=0,0"],
        )
        context = browser.new_context(no_viewport=True, locale="zh-CN")
        page = context.new_page()

        # Console listener: capture all types
        def _on_console(msg):
            level = msg.type.upper()  # error / warning / info / log / debug
            text = msg.text
            url = page.url
            _write(f"[{level}] url={url} :: {text}")

        page.on("console", _on_console)

        # Page error (uncaught exception)
        def _on_page_error(err):
            _write(f"[PAGE_ERROR] url={page.url} :: {err}")

        page.on("pageerror", _on_page_error)

        # Navigation
        def _on_nav(frame):
            if frame == page.main_frame:
                _write(f"[NAV] {frame.url}")

        page.on("framenavigated", _on_nav)

        # Failed requests
        def _on_req_fail(req):
            _write(f"[REQFAIL] {req.method} {req.url} :: {req.failure}")

        page.on("requestfailed", _on_req_fail)

        # Playwright doesn't expose a global click listener, so we inject
        # a document-level click handler that captures a short descriptor.
        def _inject_click_listener():
            try:
                page.evaluate(
                    """
                    () => {
                      window.__gaf_click_log = [];
                      document.addEventListener('click', (e) => {
                        const t = e.target;
                        if (!t) return;
                        const desc = [
                          t.tagName,
                          t.id ? '#' + t.id : '',
                          t.className && typeof t.className === 'string'
                            ? '.' + t.className.split(/\\s+/).filter(Boolean).slice(0, 3).join('.')
                            : '',
                          t.getAttribute('role') ? '[role=' + t.getAttribute('role') + ']' : '',
                          t.getAttribute('aria-label') ? '[aria=' + t.getAttribute('aria-label') + ']' : '',
                          t.getAttribute('href') ? '[href=' + t.getAttribute('href') + ']' : '',
                        ].join('');
                        const path = window.location.pathname + window.location.hash;
                        window.__gaf_click_log.push({ path, desc, ts: Date.now() });
                      }, true);
                    }
                    """
                )
            except Exception as exc:
                _write(f"[INJECT_FAIL] {exc}")

        # Login flow
        _write("[STEP] navigating to login page")
        page.goto(LOGIN_URL, wait_until="networkidle")
        _inject_click_listener()

        _write("[STEP] filling credentials")
        page.locator('input[autocomplete="username"]').fill("admin")
        page.locator('input[autocomplete="current-password"]').fill("admin123")
        page.locator('button[type="submit"]').click()

        try:
            page.wait_for_url("**/dashboard", timeout=10000)
            _write(f"[OK] logged in, dashboard url={page.url}")
            _inject_click_listener()
        except Exception as exc:
            _write(f"[LOGIN_FAIL] {exc}")

        # Re-inject click listener on every navigation (SPA route change)
        def _on_nav_reinject(frame):
            if frame == page.main_frame:
                _inject_click_listener()

        page.on("framenavigated", _on_nav_reinject)

        # Periodically flush captured clicks to the log file
        def _click_drain():
            while True:
                try:
                    clicks = page.evaluate(
                        "() => { const c = window.__gaf_click_log || []; "
                        "window.__gaf_click_log = []; return c; }"
                    )
                    for c in clicks or []:
                        _write(f"[CLICK] path={c.get('path','')} desc={c.get('desc','')}")
                except Exception:
                    pass
                time.sleep(1.0)

        threading.Thread(target=_click_drain, daemon=True).start()

        _write("[READY] browser open — user can start clicking. Close the Chrome window to stop monitoring.")

        # Block until the browser is closed by the user
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass

        _write("[STOP] page closed")
        browser.close()

    with _log_lock:
        _log_file.write(f"==== Console monitor stopped at {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n")
        _log_file.flush()
        _log_file.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
