"""e2e scenarios package."""
from scripts.e2e.scenarios.ai_qa_chat import run_ai_qa_chat
from scripts.e2e.scenarios.browser_login import run_browser_login
from scripts.e2e.scenarios.devices_control_mode import run_devices_control_mode
from scripts.e2e.scenarios.full_routes import run_full_routes

__all__ = [
    "run_ai_qa_chat",
    "run_browser_login",
    "run_devices_control_mode",
    "run_full_routes",
]
