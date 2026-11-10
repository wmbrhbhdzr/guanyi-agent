"""Window discovery and client-area pixel capture; no game-state access."""

from .windows import CaptureError, WindowInfo, WindowsCapture

__all__ = ["CaptureError", "WindowInfo", "WindowsCapture"]
