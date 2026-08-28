"""
Handler module: screenshot + verify handlers.
"""
from .screenshot import ScreenshotHandler, ScreenshotResult
from .verify import VerifyHandler, VerifyResult, VerifyType

__all__ = [
    'ScreenshotHandler',
    'ScreenshotResult',
    'VerifyHandler',
    'VerifyResult',
    'VerifyType',
]
