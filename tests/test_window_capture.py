"""Window session behavior with pixel fixtures; no desktop or network required."""

import tempfile
import threading
import time
import unittest
from pathlib import Path

from PIL import Image

from guanyi.capture import CaptureError, WindowInfo
from guanyi.capture.windows import classify_window
from guanyi.app.window_vision_service import WindowVisionService


class FakeBackend:
    def __init__(self):
        self.window = WindowInfo(10, 100, "Slay the Spire 2", "SlayTheSpire2.exe", "sts2", True)
        self.picture = Image.new("RGB", (400, 240), "#456789")
        self.error = None
    def list_windows(self):
        return [self.window]
    def capture(self, window):
        if self.error:
            raise self.error
        return self.picture.copy(), self.window


class FakeVision:
    def __init__(self):
        self.calls = []
    def recognize(self, path, game):
        self.calls.append((path, game))
        return {"ok": True, "status": "recognized", "summary": "test", "observation": {}, "warnings": []}


class WindowCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="guanyi-capture-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = FakeBackend(); self.vision = FakeVision()
        self.service = WindowVisionService(self.vision, self.backend, self.root)

    def test_01_discovery_classifies_game_but_not_similar_editor_title(self):
        self.assertEqual(classify_window("Slay the Spire 2", "x.exe"), ("sts2", True))
        self.assertEqual(classify_window("x", "SlayTheSpire2.exe"), ("sts2", True))
        self.assertEqual(classify_window("Slay the Spire 2 - README - VSCode", "Code.exe"), ("generic", False))
        self.assertEqual(classify_window("Plants vs Zombies", "PlantsVsZombies.exe"), ("generic", True))

    def test_02_preview_saves_only_target_pixels_and_never_requests_model(self):
        result = self.service.run_once(self.backend.window, recognize=False)
        self.assertEqual(result["status"], "captured")
        self.assertEqual(self.vision.calls, [])
        with Image.open(result["capture_path"]) as picture:
            self.assertEqual(picture.size, (400, 240))
            self.assertEqual(picture.getpixel((0, 0)), (69, 103, 137))
        self.assertEqual(result["capture"]["method"], "PrintWindow-client")
        self.assertTrue(Path(result["capture_path"]).with_name("capture.json").is_file())

    def test_03_auto_uses_detected_profile_without_title_in_client_image(self):
        result = self.service.run_once(self.backend.window)
        self.assertTrue(result["ok"])
        self.assertEqual(self.vision.calls[0][1], "sts2")

    def test_04_manual_generic_is_respected(self):
        self.service.run_once(self.backend.window, game="generic")
        self.assertEqual(self.vision.calls[0][1], "generic")

    def test_05_unchanged_pixels_skip_cloud_and_changed_pixels_upload(self):
        first = self.service.run_once(self.backend.window)
        same = self.service.run_once(self.backend.window, previous_hash=first["capture_hash"])
        self.assertEqual(same["status"], "unchanged")
        self.assertEqual(len(self.vision.calls), 1)
        self.backend.picture.putpixel((1, 1), (0, 0, 0))
        changed = self.service.run_once(self.backend.window, previous_hash=first["capture_hash"])
        self.assertTrue(changed["ok"])
        self.assertEqual(len(self.vision.calls), 2)

    def test_06_closed_minimized_and_timeout_do_not_upload(self):
        for code in ("window_closed", "window_minimized", "capture_timeout", "window_changed"):
            self.backend.error = CaptureError(code, code)
            result = self.service.run_once(self.backend.window)
            self.assertEqual(result["error"]["code"], code)
        self.assertEqual(self.vision.calls, [])

    def test_07_black_frame_refused_before_cloud(self):
        self.backend.picture = Image.new("RGB", (400, 240), "black")
        result = self.service.run_once(self.backend.window)
        self.assertFalse(result["ok"])
        self.assertEqual(self.vision.calls, [])

    def test_08_stopped_before_capture_never_uploads(self):
        cancel = threading.Event(); cancel.set()
        result = self.service.run_once(self.backend.window, cancel=cancel)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(self.vision.calls, [])

    def test_09_stop_during_capture_prevents_upload(self):
        cancel = threading.Event()
        original = self.backend.capture
        def capture(window):
            cancel.set()
            return original(window)
        self.backend.capture = capture
        result = self.service.run_once(self.backend.window, cancel=cancel)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(self.vision.calls, [])

    def test_10_concurrent_cycle_is_refused(self):
        self.service._lock.acquire()
        try:
            result = self.service.run_once(self.backend.window)
            self.assertEqual(result["error"]["code"], "capture_busy")
            self.assertEqual(self.vision.calls, [])
        finally:
            self.service._lock.release()

    def test_11_stop_after_cloud_discards_late_answer(self):
        cancel = threading.Event()
        original = self.vision.recognize
        def recognize(path, game):
            cancel.set()
            return original(path, game)
        self.vision.recognize = recognize
        result = self.service.run_once(self.backend.window, cancel=cancel)
        self.assertEqual(result["status"], "stopped")
        self.assertTrue(result["stopped_after_request"])

    def test_12_capture_failure_does_not_switch_to_another_window(self):
        selected = self.backend.window
        self.backend.error = CaptureError("window_closed", "closed")
        result = self.service.run_once(selected)
        self.assertEqual(result["error"]["code"], "window_closed")
        self.assertIsNone(result["capture_path"])
        self.assertEqual(self.vision.calls, [])

    def test_13_native_wait_timeout_keeps_worker_lock(self):
        from guanyi.capture import WindowsCapture
        native = WindowsCapture.__new__(WindowsCapture)
        native.u = object()
        native._lock = threading.Lock(); native.timeout_s = .02
        release = threading.Event(); done = threading.Event()
        def slow(window):
            release.wait(2); done.set()
            return self.backend.picture, window
        native._capture = slow
        try:
            with self.assertRaises(CaptureError) as first:
                native.capture(self.backend.window)
            self.assertEqual(first.exception.code, "capture_timeout")
            with self.assertRaises(CaptureError) as second:
                native.capture(self.backend.window)
            self.assertEqual(second.exception.code, "capture_busy")
        finally:
            release.set(); self.assertTrue(done.wait(2))

    def test_14_native_reused_handle_refused_before_rendering(self):
        from guanyi.capture import WindowsCapture
        native = WindowsCapture.__new__(WindowsCapture)
        native.info = lambda hwnd: WindowInfo(hwnd, 999, "other", "other.exe")
        with self.assertRaises(CaptureError) as caught:
            native._capture(self.backend.window)
        self.assertEqual(caught.exception.code, "window_changed")
