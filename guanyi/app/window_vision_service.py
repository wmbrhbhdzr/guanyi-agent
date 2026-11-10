"""One serialized cycle: selected window -> pixels -> existing vision service."""

import hashlib
import json
import threading
import time
import uuid
from pathlib import Path

from ..capture import CaptureError, WindowsCapture
from ..vision.images import ImageInputError, prepare_image
from .vision_service import VisionService


class WindowVisionService:
    def __init__(self, vision=None, capture=None, out_dir="data/window_capture"):
        self.vision = vision if vision is not None else VisionService()
        self.capture_backend = capture  # Lazy to keep file recognition portable.
        self.out_dir = Path(out_dir)
        self._lock = threading.Lock()

    @property
    def backend(self):
        if self.capture_backend is None:
            self.capture_backend = WindowsCapture()
        return self.capture_backend

    def list_windows(self):
        return self.backend.list_windows()

    def run_once(self, window, game="auto", recognize=True, previous_hash=None, cancel=None):
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "status": "failed", "error": {"code": "capture_busy", "message": "采集识别仍在进行，请等待完成"}}
        started = time.monotonic()
        result = {"ok": False, "status": "failed", "error": None, "capture_path": None}
        folder = None
        cancel = cancel if cancel is not None else threading.Event()
        try:
            if cancel.is_set():
                return {**result, "status": "stopped"}
            picture, current = self.backend.capture(window)
            if cancel.is_set():
                return {**result, "status": "stopped"}
            digest = hashlib.sha256(picture.tobytes() + str(picture.size).encode("ascii")).hexdigest()
            metadata = {**current.to_dict(), "method": "PrintWindow-client", "size": list(picture.size),
                        "pixel_sha256": digest}
            result.update(capture=metadata, capture_hash=digest)
            if previous_hash == digest:
                return {**result, "ok": True, "status": "unchanged"}
            folder = self.out_dir / ("capture-" + uuid.uuid4().hex)
            folder.mkdir(parents=True, exist_ok=False)
            path = folder / "input.png"; picture.save(path)
            # Reject blank/corrupt frames before upload; validates rendered pixels.
            prepare_image(path)
            result["capture_path"] = str(path)
            if cancel.is_set():
                result["status"] = "stopped"
                return result
            if not recognize:
                result.update(ok=True, status="captured")
            else:
                effective = current.profile if game == "auto" and current.supported and current.profile != "generic" else game
                result = {**self.vision.recognize(path, game=effective),
                          "capture_path": str(path), "capture": metadata, "capture_hash": digest}
                if cancel.is_set():
                    result.update(status="stopped", stopped_after_request=True)
            return result
        except (CaptureError, ImageInputError, OSError) as exc:
            result["error"] = {"code": getattr(exc, "code", "invalid_capture"), "message": str(exc)}
            return result
        finally:
            result["capture_elapsed_ms"] = round((time.monotonic()-started)*1000, 1)
            if folder is not None:
                try:
                    (folder/"capture.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                except OSError:
                    result.setdefault("warnings", []).append("窗口采集日志未能保存")
            self._lock.release()
