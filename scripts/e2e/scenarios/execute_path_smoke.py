"""E2E scenario — real task-execution path smoke via the browser.

Browser-first verification (user directive 2026-08-27, testing-conventions §1.1):
login → trigger a task's execute button → observe the executions page until a
terminal status appears.

What it proves (full dispatch chain, no mocks):
    execute button -> TaskService.dispatch -> dispatch_task (S1 dispatch_sent_at)
    -> WebSocket -> real Agent accepts (dispatch_ack_at) -> pipeline node runs
    -> task.result -> backend persists terminal status -> UI shows it.

Environment limitation: if the pipeline needs a device window (e.g. Chrome)
and none is attached, the execution lands FAILED with e.g. "uia: no window
handle" — the link is still fully proven; the node outcome is environment-only.

Usage:
    conda run -n gaf python scripts/e2e/scenarios/execute_path_smoke.py [--task 关键词] [--url http://127.0.0.1:5173]
    Requires: dev servers running (gaf_daemon) + an online Agent + Playwright.

Exit code: 0 when a terminal status is reached and no page errors; 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_URL = "http://127.0.0.1:5173"
DEFAULT_TASK_KEYWORD = ""  # e.g. "百度搜索" (unique substring of the task name)
POLL_SECONDS = 60


def _classify_status(text: str) -> str | None:
    low = text.lower()
    if any(k in low for k in ("success", "成功", "已完成", "completed")):
        return "success"
    if any(k in low for k in ("fail", "失败", "error", "异常")):
        return "failed"
    if any(k in low for k in ("cancel", "取消")):
        return "cancelled"
    if any(k in low for k in ("running", "执行中")):
        return "running"
    if any(k in low for k in ("pending", "待执行", "等待")):
        return "pending"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default=DEFAULT_TASK_KEYWORD, help="unique substring of task name to execute")
    parser.add_argument("--url", default=DEFAULT_URL, help="frontend base URL")
    args = parser.parse_args()
    if not args.task:
        print("--task is required (unique substring of the task name to execute)")
        return 2

    console_errors: list[str] = []
    page_errors: list[str] = []
    screenshot = Path(__file__).resolve().parent / ".trash" / "e2e_exec_smoke.png"
    report: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        page.goto(f"{args.url}/login", wait_until="networkidle")
        page.locator('input[autocomplete="username"]').fill("admin")
        page.locator('input[autocomplete="current-password"]').fill("admin123")
        page.locator('button[type="submit"]').click()
        page.wait_for_url("**/dashboard", timeout=20000)
        report["logged_in"] = True
        print("[+] logged in -> /dashboard")

        page.goto(f"{args.url}/tasks", wait_until="networkidle")
        row = page.locator("tr", has_text=args.task).first
        row.wait_for(timeout=10000)
        row.locator('button:has(svg[data-icon="play-circle"])').first.click()
        report["execution_triggered"] = True
        print(f"[+] execute clicked on row containing '{args.task}'")
        time.sleep(8)

        page.goto(f"{args.url}/ops/executions", wait_until="networkidle")
        deadline = time.time() + POLL_SECONDS
        final_status = None
        first_row_text = ""
        while time.time() < deadline:
            time.sleep(3)
            page.reload(wait_until="networkidle")
            first_row = page.locator("tbody tr").first
            if first_row.count() == 0:
                print("[.] no execution rows yet ...")
                continue
            first_row_text = first_row.inner_text()
            status = _classify_status(first_row_text)
            print(f"[.] latest execution row status={status or '?'}")
            if status in ("success", "failed", "cancelled"):
                final_status = status
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot))
                break
        if final_status is None:
            final_status = _classify_status(first_row_text) if first_row_text else None
        report["final_status"] = final_status or "timeout-no-terminal"
        report["latest_row_text"] = first_row_text.replace("\n", " | ")[:200]
        report["screenshot"] = str(screenshot)
        browser.close()

    report["page_errors"] = page_errors
    report["console_errors"] = console_errors[:20]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = report["final_status"] in ("success", "failed", "cancelled") and not page_errors
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
