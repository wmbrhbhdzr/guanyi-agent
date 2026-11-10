"""Drive only our own Tk window; no actual games, cloud calls or desktop input."""

import tempfile
import time
import unittest
from pathlib import Path

from guanyi.app.window_vision_service import WindowVisionService
from guanyi.app.service import SessionService
from guanyi.app.logging_setup import reset_loggers
from guanyi.data.store import JsonlStore
from guanyi.ui.main_window import GuanyiApp
from test_window_capture import FakeBackend, FakeVision


class WindowUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="guanyi-window-ui-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = FakeBackend(); self.vision = FakeVision()
        self.app = GuanyiApp(service=SessionService(JsonlStore(self.root/"runs")), vision=self.vision)
        self.app.withdraw()
        self.panel = self.app.vision_panel
        self.panel.window_service = WindowVisionService(self.vision, self.backend, self.root/"capture")
        self.panel.refresh_windows(True)
        self.addCleanup(reset_loggers)
        self.addCleanup(self.app.destroy)

    def pump(self, seconds=.15):
        end = time.monotonic()+seconds
        while time.monotonic()<end:
            self.app.update(); time.sleep(.005)

    def test_01_auto_connect_and_preview_no_cloud(self):
        self.assertEqual(self.panel.selected_window.hwnd, 10)
        self.panel.capture_window(False); self.pump()
        self.assertEqual(self.panel.result["status"], "captured")
        self.assertEqual(self.vision.calls, [])

    def test_02_unchanged_cycle_and_stop(self):
        self.panel.interval_var.set("1"); self.panel.start_continuous(); self.pump(1.4)
        self.assertEqual(len(self.vision.calls), 1)
        self.assertEqual(self.panel.result["status"], "unchanged")
        self.panel.stop_continuous()
        self.assertIsNone(self.panel._cycle_id)
        self.assertFalse(self.panel.continuous)

    def test_03_invalid_interval_does_not_start(self):
        for value in ("0", "nan", "bad", "301"):
            self.panel.interval_var.set(value); self.panel.start_continuous()
            self.assertFalse(self.panel.continuous)
        self.assertEqual(self.vision.calls, [])

    def test_04_multiple_games_require_selection(self):
        from guanyi.capture import WindowInfo
        one = self.backend.window
        another = WindowInfo(11, 101, "Slay the Spire 2", "SlayTheSpire2.exe", "sts2", True)
        self.backend.list_windows = lambda: [one, another]
        self.panel.refresh_windows(True)
        self.assertIsNone(self.panel.selected_window)
        self.panel.window_var.set(another.label); self.panel.select_window()
        self.assertEqual(self.panel.selected_window.hwnd, 11)

    def test_05_capture_error_stops_continuous(self):
        from guanyi.capture import CaptureError
        self.backend.error = CaptureError("window_closed", "窗口已关闭")
        self.panel.start_continuous(); self.pump()
        self.assertFalse(self.panel.continuous)
        self.assertIsNone(self.panel._cycle_id)
        self.assertEqual(self.panel.result["error"]["code"], "window_closed")
        self.assertEqual(self.vision.calls, [])
