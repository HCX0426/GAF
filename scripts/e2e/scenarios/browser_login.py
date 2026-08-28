"""frontend_login — End-to-end browser login scenario.

Requires Playwright + Chromium (managed by ``playwright install chromium``).

The scenario launches a headless browser, navigates to the local Vite dev
server, logs in with the default admin credentials, asserts that the URL
switches to ``/dashboard``, and records any console errors or page-level
JavaScript exceptions.
"""
from __future__ import annotations

import os
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173")
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"


def run_browser_login(
    repo: Path,
    frontend_url: str = DEFAULT_FRONTEND_URL,
    username: str = DEFAULT_USERNAME,
    password: str = DEFAULT_PASSWORD,
) -> tuple[bool, str]:
    """Run the browser login scenario.

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

            page.goto(f"{frontend_url}/login", wait_until="networkidle")
            page.locator('input[autocomplete="username"]').fill(username)
            page.locator('input[autocomplete="current-password"]').fill(password)
            page.locator('button[type="submit"]').click()
            page.wait_for_url("**/dashboard", timeout=10000)

            browser.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"browser automation failed: {exc}\n{traceback.format_exc(limit=2)}"

    if page_errors:
        return False, f"page JS exceptions: {page_errors}"
    if console_errors:
        return False, f"console errors: {console_errors}"

    return True, f"login OK → {frontend_url}/dashboard (no JS errors)"
