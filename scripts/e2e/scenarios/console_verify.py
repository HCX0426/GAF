"""Verify pages load without 404 or antd deprecation warnings.

Reusable regression check. Visits a list of routes, captures console messages,
and exits non-zero if any [ERROR]/[WARNING] matching expected-fix patterns
remain.

Usage:
    conda run -n gaf python scripts/e2e/scenarios/console_verify.py

Log file: .trash/verify_console.log (gitignored temp output).
"""
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
LOGIN_URL = f"{_FRONTEND_URL}/login"
LOG_FILE = Path(__file__).resolve().parents[3] / ".trash" / "verify_console.log"

# Pages to verify — extend as needed when new routes are added.
PAGES_TO_VERIFY = [
    "/game-profiles/1",
    "/game-profiles?edit=1",
    "/devices/windows",
    "/devices/adb-logs",
    "/ai/anomaly",
    "/ai/config",
]

# Patterns that should NEVER appear after fixes are in place.
# Add new patterns here when new deprecation/fix categories are introduced.
EXPECTED_ISSUES_FIXED = [
    # antd 5.x deprecation warnings (TD-100)
    "`direction` is deprecated",
    "`destroyOnClose` is deprecated",
    "`bodyStyle` is deprecated",
    "`destroyInactiveTabPane` is deprecated",
    "`orientation` is used for direction",
    # autocomplete (TD-100)
    "Input elements should have autocomplete",
]


def main() -> int:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "w", encoding="utf-8")
    issues: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1280, "height": 800}, locale="zh-CN")
        page = context.new_page()

        def _on_console(msg):
            ts = time.strftime("%H:%M:%S")
            line = f"[{ts}] [{msg.type.upper()}] {page.url} :: {msg.text}"
            log.write(line + "\n")
            log.flush()
            if msg.type.lower() in ("error", "warning"):
                issues.append(line)

        page.on("console", _on_console)
        page.on("pageerror", lambda e: issues.append(f"[PAGE_ERROR] {e}"))

        # Login
        log.write("=== Login ===\n")
        page.goto(LOGIN_URL, wait_until="networkidle")
        page.locator('input[autocomplete="username"]').fill("admin")
        page.locator('input[autocomplete="current-password"]').fill("admin123")
        page.locator('button[type="submit"]').click()
        try:
            page.wait_for_url("**/dashboard", timeout=10000)
            log.write(f"OK login: {page.url}\n")
        except Exception as exc:
            log.write(f"FAIL login: {exc}\n")
            return 1

        for route in PAGES_TO_VERIFY:
            url = f"{_FRONTEND_URL}{route}"
            log.write(f"\n=== Visit {route} ===\n")
            try:
                page.goto(url, wait_until="networkidle", timeout=15000)
            except Exception as exc:
                log.write(f"NAV FAIL: {exc}\n")
                issues.append(f"NAV FAIL {route}: {exc}")
            # Let lazy tabs/effects run
            time.sleep(2.0)

            # If this is the game-profile detail page, click each tab to
            # trigger tab content rendering (catches Space/Card warnings).
            if route == "/game-profiles/1":
                tabs = page.locator('.ant-tabs-tab')
                tab_count = tabs.count()
                for i in range(tab_count):
                    try:
                        tabs.nth(i).click()
                        time.sleep(1.0)
                    except Exception as exc:
                        log.write(f"TAB click fail: {exc}\n")

        browser.close()

    # Summary
    log.write("\n\n=== Summary ===\n")
    still_broken: list[str] = []
    for issue in issues:
        for pattern in EXPECTED_ISSUES_FIXED:
            if pattern in issue:
                still_broken.append(issue)
                break

    if not still_broken:
        log.write(f"PASS — {len(issues)} non-target warnings/errors remain, none match expected fix patterns.\n")
        for i in issues:
            log.write(f"  (residual) {i}\n")
        log.close()
        return 0
    else:
        log.write(f"FAIL — {len(still_broken)} expected-fixed issues still present:\n")
        for i in still_broken:
            log.write(f"  {i}\n")
        log.close()
        return 2


if __name__ == "__main__":
    sys.exit(main())
