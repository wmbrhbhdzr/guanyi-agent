"""Exercise real Win32 capture against an owned test window, never other apps.

The fixture displays a saved evaluation image, not a live game. --online additionally
checks capture -> model -> saved observation; default is offline native capture only.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fixture(ready):
    from guanyi.ui.main_window import _ensure_tcl_env
    _ensure_tcl_env()
    import ctypes
    user32 = ctypes.WinDLL("user32")
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    import tkinter as tk
    from PIL import Image, ImageTk
    app = tk.Tk(); app.title("GuanYi Native Capture Fixture")
    app.maxsize(8192, 8192)
    image = Image.open(ROOT/"evaluation/exp7/inputs/E10.png").convert("RGB")
    # Preserve source pixels: downscaling here can make HUD text harder to read.
    picture = ImageTk.PhotoImage(image, master=app)
    tk.Label(app, image=picture, borderwidth=0, highlightthickness=0).pack()
    app.geometry("%dx%d+20+20" % image.size)
    app.update()
    u = ctypes.WinDLL("user32"); u.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]; u.GetAncestor.restype = ctypes.c_void_p
    hwnd = u.GetAncestor(app.winfo_id(), 2)
    Path(ready).write_text(json.dumps({"hwnd": hwnd, "pid": os.getpid(), "size": list(image.size)}), encoding="utf-8")
    app.after(120000, app.destroy)
    app.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture")
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()
    if args.fixture:
        return fixture(args.fixture)
    from guanyi.capture import WindowsCapture, CaptureError
    from guanyi.app.window_vision_service import WindowVisionService
    with tempfile.TemporaryDirectory(prefix="guanyi-native-fixture-") as directory:
        ready = Path(directory)/"ready.json"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(sys.prefix)/"Lib/site-packages")
        # Launch the interpreter directly: Windows venv launchers can spawn a different PID.
        executable = getattr(sys, "_base_executable", sys.executable)
        process = subprocess.Popen([executable, "-B", str(Path(__file__).resolve()), "--fixture", str(ready)],
                                   cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic()+10
            while not ready.exists() and time.monotonic()<deadline:
                time.sleep(.05)
            if not ready.exists(): raise RuntimeError("test window did not start")
            info = json.loads(ready.read_text(encoding="utf-8"))
            backend = WindowsCapture()
            window = next(w for w in backend.list_windows() if w.pid == info["pid"])
            service = WindowVisionService(capture=backend)
            result = service.run_once(window, recognize=args.online, game="sts2")
            assert result["ok"], result
            # Client dimensions must match rendered image dimensions, excluding all decorations.
            assert result["capture"]["size"] == info["size"], (result["capture"], info)
            from PIL import Image
            with Image.open(result["capture_path"]) as actual, Image.open(ROOT/"evaluation/exp7/inputs/E10.png") as expected:
                assert actual.convert("RGB").tobytes() == expected.convert("RGB").tobytes(), "client pixels changed"
            print(json.dumps({"fixture": True, "live_game": False, "online": args.online,
                "status": result["status"], "size": result["capture"]["size"],
                "capture_path": result["capture_path"], "result_path": result.get("saved_path"),
                "summary": result.get("summary")}, ensure_ascii=False, indent=2))
            backend.u.ShowWindow.argtypes = [__import__('ctypes').c_void_p, __import__('ctypes').c_int]
            backend.u.ShowWindow(window.hwnd, 6)
            time.sleep(.1)
            try:
                backend.capture(window)
                raise AssertionError("minimized capture should fail")
            except CaptureError as exc:
                assert exc.code == "window_minimized", exc.code
                print("Minimized window: correctly refused")
            process.terminate(); process.wait(timeout=5)
            try:
                backend.capture(window)
                raise AssertionError("closed capture should fail")
            except CaptureError as exc:
                assert exc.code == "window_closed", exc.code
                print("Closed window: correctly refused")
        finally:
            if process.poll() is None:
                process.terminate(); process.wait(timeout=5)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
