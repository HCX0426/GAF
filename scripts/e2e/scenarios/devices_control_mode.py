"""devices_control_mode — End-to-end browser scenario for TD-015.

Requires Playwright + Chromium (managed by ``playwright install chromium``).

The scenario logs into the local Vite dev server, navigates to
``/devices/windows``, verifies that the control-mode selector renders
(with or without registered devices), switches the mode if a device is
present, and records any console errors or page-level JS exceptions.
"""
from __future__ import annotations

import os
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173")
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"


def run_devices_control_mode(
    repo: Path,
    frontend_url: str = DEFAULT_FRONTEND_URL,
    username: str = DEFAULT_USERNAME,
    password: str = DEFAULT_PASSWORD,
) -> tuple[bool, str]:
    """Run the devices control mode scenario.

    Returns ``(ok, detail)`` so it can be wired into ``e2e/run_all.py``.
    """
    console_messages: list[str] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})

            def _on_console(msg: object) -> None:
                text = f"[{msg.type}] {msg.text}"  # type: ignore[attr-defined]
                console_messages.append(text)
                if msg.type == "error":  # type: ignore[attr-defined]
                    console_errors.append(text)

            page.on("console", _on_console)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            # Login
            page.goto(f"{frontend_url}/login", wait_until="networkidle")
            page.locator('input[autocomplete="username"]').fill(username)
            page.locator('input[autocomplete="current-password"]').fill(password)
            page.locator('button[type="submit"]').click()
            page.wait_for_url("**/dashboard", timeout=10000)

            # Navigate to window management page
            page.goto(f"{frontend_url}/devices/windows", wait_until="networkidle")

            # Wait for either the control-mode selector or the empty state.
            selector = page.locator('[data-testid="control-mode-select"]').first
            empty_state = page.locator('.ant-empty').first
            try:
                selector.wait_for(state="visible", timeout=5000)
                has_selector = True
            except Exception:
                try:
                    empty_state.wait_for(state="visible", timeout=3000)
                    has_selector = False
                except Exception:
                    return False, "control-mode selector and empty state both missing on /devices/windows"

            if has_selector:
                # Switch to a different mode and back to exercise the UI.
                # Ant Design renders option labels as translated Tags (zh-CN here).
                selector.click()
                page.locator('.ant-select-dropdown .ant-select-item:has-text("前台")').click()
                page.wait_for_timeout(300)
                selector.click()
                page.locator('.ant-select-dropdown .ant-select-item:has-text("伪后台")').click()
                page.wait_for_timeout(300)
                detail = "control mode selector rendered and toggled"
            else:
                detail = "no registered windows (empty state); page rendered without JS errors"

            browser.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"browser automation failed: {exc}\n{traceback.format_exc(limit=2)}"

    if page_errors:
        return False, f"page JS exceptions: {page_errors}"
    if console_errors:
        return False, f"console errors: {console_errors}"

    return True, f"devices/windows OK → {detail} (no JS errors)"
