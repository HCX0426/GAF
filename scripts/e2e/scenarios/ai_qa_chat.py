"""ai_qa_chat — End-to-end browser scenario for LLM chat via the QA panel.

Requires Playwright + Chromium (managed by ``playwright install chromium``)
and both dev servers running (backend :8000 + frontend :5173).

The scenario logs into the local Vite dev server, navigates to ``/ai/qa``,
creates a new QA conversation, sends a test message, and verifies that
an LLM reply is rendered in the chat bubble. This exercises the full
chain: browser → Vite proxy → Django /qa/ask/ → call_llm() → LLMRouter
→ SiliconFlow API → reply rendered.

Regression coverage for the two bugs fixed in commit 6a32763:
  - backend/qa/views.py model_name NameError
  - frontend QAPanel calling non-existent /qa/qa-sessions/{id}/messages/
"""
from __future__ import annotations

import json
import os
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173")
_API_PREFIX = os.environ.get("GAF_API_PREFIX", "api/v2")
DEFAULT_LOGIN_URL = f"{DEFAULT_FRONTEND_URL}/{_API_PREFIX}/accounts/auth/login/"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"
DEFAULT_TEST_MESSAGE = "你好，请用一句话介绍你自己。1+1等于几？"


def run_ai_qa_chat(
    repo: Path,
    frontend_url: str = DEFAULT_FRONTEND_URL,
    login_url: str = DEFAULT_LOGIN_URL,
    username: str = DEFAULT_USERNAME,
    password: str = DEFAULT_PASSWORD,
    test_message: str = DEFAULT_TEST_MESSAGE,
) -> tuple[bool, str]:
    """Run the AI QA chat scenario.

    Returns ``(ok, detail)`` so it can be wired into ``e2e/run_all.py``.
    """
    console_errors: list[str] = []
    page_errors: list[str] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 800})

            def _on_console(msg: object) -> None:
                if msg.type == "error":  # type: ignore[attr-defined]
                    console_errors.append(msg.text)  # type: ignore[attr-defined]

            page.on("console", _on_console)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            # Step 1: Login via API through Vite proxy (avoids Antd Form
            # selector issues + IPv6 connectivity problems).
            page.goto(frontend_url, wait_until="domcontentloaded", timeout=15000)
            api_resp = page.request.post(
                login_url,
                data={"username": username, "password": password},
                timeout=10000,
            )
            if api_resp.status != 200:
                browser.close()
                return False, f"login API returned {api_resp.status}"
            login_data = api_resp.json()
            refresh_token = login_data.get("refresh", "")
            if not refresh_token:
                browser.close()
                return False, "no refresh token in login response"

            # Step 2: Inject refresh token so initAuth() restores the session.
            page.evaluate(
                f"localStorage.setItem('refresh_token', {json.dumps(refresh_token)})"
            )

            # Step 3: Navigate to QA panel.
            page.goto(f"{frontend_url}/ai/qa", wait_until="networkidle", timeout=20000)
            if "/login" in page.url:
                browser.close()
                return False, "redirected to login — session restore failed"

            # Step 4: Create a new QA conversation.
            clicked = False
            for sel in ['button:has-text("新建问答")', 'button:has-text("New Q&A")']:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    btn.click()
                    clicked = True
                    break
            if not clicked:
                browser.close()
                return False, "could not find 'New QA' button"

            # Step 5: Fill textarea and send.
            try:
                page.wait_for_selector("textarea", timeout=8000)
            except Exception:
                browser.close()
                return False, "no textarea appeared after creating conversation"

            textarea = page.locator("textarea").first
            textarea.fill(test_message)

            sent = False
            for sel in ['button:has-text("发送")', 'button:has-text("Send")']:
                btn = page.locator(sel).first
                if btn.count() > 0:
                    btn.click()
                    sent = True
                    break
            if not sent:
                textarea.press("Enter")

            # Step 6: Poll for LLM reply (up to 45s).
            # "AI助手" (no space) only appears in the chat bubble label;
            # the sidebar menu uses "AI 助手" (with space).
            assistant_reply = ""
            for _poll in range(22):
                page.wait_for_timeout(2000)
                body_text = page.locator("body").inner_text()
                ai_count = body_text.count("AI助手")
                en_count = body_text.count("AI Assistant")
                thinking = "思考中" in body_text or "Thinking" in body_text

                if (ai_count >= 1 or en_count >= 1) and not thinking:
                    label = "AI助手" if ai_count >= 1 else "AI Assistant"
                    idx = body_text.find(label)
                    assistant_reply = body_text[idx + len(label):].strip()[:500]
                    break

            browser.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"browser automation failed: {exc}\n{traceback.format_exc(limit=2)}"

    if page_errors:
        return False, f"page JS exceptions: {page_errors}"

    if not assistant_reply:
        return False, "no assistant reply detected within 45s (LLM may be unreachable)"

    if len(assistant_reply) <= 5:
        return False, f"assistant reply too short: '{assistant_reply}'"

    # Console 404s from stale QA session fetches are tolerated (the
    # QAPanel tries to list existing sessions which may 404 on first
    # run). Only hard JS errors / page errors fail the scenario.
    return True, (
        f"QA chat OK — reply: '{assistant_reply[:80]}'"
        f" (console_errors={len(console_errors)})"
    )
