"""Win32 client-area rendering. Never fall back to a desktop screenshot."""

import ctypes as C
from ctypes import wintypes as W
from dataclasses import asdict, dataclass
from pathlib import PureWindowsPath
import os
import sys
import threading
import math

from PIL import Image

from ..agent.runtime import wait_call


class CaptureError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    title: str
    process: str
    profile: str = "generic"
    supported: bool = False

    def to_dict(self):
        return asdict(self)

    @property
    def label(self):
        return "%s%s [%s · PID %d · 0x%x]" % (
            "★ " if self.supported else "", self.title, self.process or "进程名不可读", self.pid, self.hwnd)


def classify_window(title, process):
    name = process.lower()
    normalized = title.lower().replace(" ", "")
    if name in ("slaythespire2.exe", "slaythespire2", "sts2.exe") or normalized in ("slaythespire2", "杀戮尖塔2"):
        return "sts2", True
    if name in ("plantsvszombies.exe", "plantsvszombies", "pvz.exe") or normalized in ("plantsvszombies", "植物大战僵尸"):
        return "generic", True  # Window discovery supported; PVZ semantic adapter is separate.
    return "generic", False


class WindowsCapture:
    def __init__(self, timeout_s=3.0):
        if sys.platform != "win32":
            raise CaptureError("unsupported_platform", "窗口采集目前仅支持Windows")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("窗口采集等待时间必须大于0")
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self.u = C.WinDLL("user32", use_last_error=True)
        self.g = C.WinDLL("gdi32", use_last_error=True)
        self.k = C.WinDLL("kernel32", use_last_error=True)
        self._bind()

    def _bind(self):
        def bind(lib, name, args, result):
            fn = getattr(lib, name); fn.argtypes = args; fn.restype = result
        self.callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        bind(self.u, "EnumWindows", [self.callback_type, W.LPARAM], W.BOOL)
        for name in ("IsWindow", "IsWindowVisible", "IsIconic"):
            bind(self.u, name, [W.HWND], W.BOOL)
        bind(self.u, "GetWindowTextLengthW", [W.HWND], C.c_int)
        bind(self.u, "GetWindowTextW", [W.HWND, W.LPWSTR, C.c_int], C.c_int)
        bind(self.u, "GetWindowThreadProcessId", [W.HWND, C.POINTER(W.DWORD)], W.DWORD)
        bind(self.u, "GetClientRect", [W.HWND, C.POINTER(W.RECT)], W.BOOL)
        bind(self.u, "GetDC", [W.HWND], W.HDC)
        bind(self.u, "ReleaseDC", [W.HWND, W.HDC], C.c_int)
        bind(self.u, "PrintWindow", [W.HWND, W.HDC, W.UINT], W.BOOL)
        bind(self.g, "CreateCompatibleDC", [W.HDC], W.HDC)
        bind(self.g, "CreateCompatibleBitmap", [W.HDC, C.c_int, C.c_int], W.HBITMAP)
        bind(self.g, "SelectObject", [W.HDC, W.HANDLE], W.HANDLE)
        bind(self.g, "DeleteObject", [W.HANDLE], W.BOOL)
        bind(self.g, "DeleteDC", [W.HDC], W.BOOL)
        bind(self.g, "GetDIBits", [W.HDC, W.HBITMAP, W.UINT, W.UINT, C.c_void_p, C.c_void_p, W.UINT], C.c_int)
        bind(self.k, "OpenProcess", [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
        bind(self.k, "QueryFullProcessImageNameW", [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL)
        bind(self.k, "CloseHandle", [W.HANDLE], W.BOOL)
        if hasattr(self.u, "SetThreadDpiAwarenessContext"):
            bind(self.u, "SetThreadDpiAwarenessContext", [C.c_void_p], C.c_void_p)

    def info(self, hwnd):
        if not hwnd or not self.u.IsWindow(hwnd):
            raise CaptureError("window_closed", "游戏窗口已关闭，请重新检测或选择窗口")
        length = self.u.GetWindowTextLengthW(hwnd)
        title = C.create_unicode_buffer(max(1, length+1))
        self.u.GetWindowTextW(hwnd, title, len(title))
        pid = W.DWORD(); self.u.GetWindowThreadProcessId(hwnd, C.byref(pid))
        process = ""
        handle = self.k.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION only
        if handle:
            try:
                size = W.DWORD(32768); buffer = C.create_unicode_buffer(size.value)
                if self.k.QueryFullProcessImageNameW(handle, 0, buffer, C.byref(size)):
                    process = PureWindowsPath(buffer.value).name
            finally:
                self.k.CloseHandle(handle)
        profile, supported = classify_window(title.value, process)
        return WindowInfo(int(hwnd), pid.value, title.value, process, profile, supported)

    def list_windows(self):
        windows = []
        @self.callback_type
        def collect(hwnd, _):
            try:
                if self.u.IsWindowVisible(hwnd):
                    item = self.info(hwnd)
                    if item.title.strip() and item.pid != os.getpid():
                        windows.append(item)
            except (CaptureError, OSError):
                pass
            return True
        self.u.EnumWindows(collect, 0)
        return sorted(windows, key=lambda item: (not item.supported, item.title.lower(), item.hwnd))

    def capture(self, selected):
        # A timed-out PrintWindow may still be running. Do not create more workers.
        if not self._lock.acquire(blocking=False):
            raise CaptureError("capture_busy", "上次窗口采集仍未结束，请稍后重试或重启观弈")
        def worker():
            previous_dpi = None
            try:
                # Per-thread awareness avoids changing Tk's UI scaling or virtualizing capture dimensions.
                if hasattr(self.u, "SetThreadDpiAwarenessContext"):
                    previous_dpi = self.u.SetThreadDpiAwarenessContext(C.c_void_p(-4))
                return self._capture(selected)
            finally:
                if previous_dpi:
                    self.u.SetThreadDpiAwarenessContext(previous_dpi)
                self._lock.release()
        try:
            return wait_call(worker, self.timeout_s)
        except TimeoutError:
            raise CaptureError("capture_timeout", "窗口绘制超过等待时间；未采集桌面，请检查游戏是否无响应") from None

    def _capture(self, selected):
        current = self.info(selected.hwnd)
        if current.pid != selected.pid or (selected.process and current.process != selected.process):
            raise CaptureError("window_changed", "窗口已被其他进程替换，请重新选择")
        if self.u.IsIconic(selected.hwnd):
            raise CaptureError("window_minimized", "游戏窗口已最小化，请恢复窗口后再采集")
        if not self.u.IsWindowVisible(selected.hwnd):
            raise CaptureError("window_hidden", "目标窗口不可见，请恢复窗口后再采集")
        rect = W.RECT()
        if not self.u.GetClientRect(selected.hwnd, C.byref(rect)):
            raise CaptureError("capture_failed", "无法读取游戏窗口大小")
        width, height = rect.right, rect.bottom
        if min(width, height) < 64 or width*height > 40_000_000:
            raise CaptureError("invalid_window_size", "窗口过小或过大，请调整游戏窗口大小")
        dc = self.u.GetDC(selected.hwnd)
        mem = self.g.CreateCompatibleDC(dc) if dc else None
        bitmap = self.g.CreateCompatibleBitmap(dc, width, height) if mem else None
        previous = None
        try:
            if not bitmap:
                raise CaptureError("capture_failed", "无法创建窗口采集缓冲区")
            previous = self.g.SelectObject(mem, bitmap)
            # PW_CLIENTONLY | PW_RENDERFULLCONTENT. No BitBlt of desktop is used.
            if not self.u.PrintWindow(selected.hwnd, mem, 3):
                raise CaptureError("capture_failed", "游戏未提供窗口画面，请尝试窗口化/无边框模式；不会回退采集桌面")
            self.g.SelectObject(mem, previous); previous = None
            class Header(C.Structure):
                _fields_ = [("size", W.DWORD), ("width", W.LONG), ("height", W.LONG),
                            ("planes", W.WORD), ("bits", W.WORD), ("compression", W.DWORD),
                            ("image_size", W.DWORD), ("x", W.LONG), ("y", W.LONG),
                            ("colors", W.DWORD), ("important", W.DWORD)]
            header = Header(C.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
            buffer = C.create_string_buffer(width*height*4)
            if self.g.GetDIBits(mem, bitmap, 0, height, buffer, C.byref(header), 0) != height:
                raise CaptureError("capture_failed", "读取窗口像素失败")
            # Recheck identity and size after rendering; refuse a moving target.
            after = self.info(selected.hwnd); after_rect = W.RECT()
            self.u.GetClientRect(selected.hwnd, C.byref(after_rect))
            if after.pid != current.pid or (after_rect.right, after_rect.bottom) != (width, height):
                raise CaptureError("window_changed", "采集过程中窗口发生变化，请重试")
            return Image.frombytes("RGB", (width, height), buffer.raw, "raw", "BGRX"), current
        finally:
            if previous: self.g.SelectObject(mem, previous)
            if bitmap: self.g.DeleteObject(bitmap)
            if mem: self.g.DeleteDC(mem)
            if dc: self.u.ReleaseDC(selected.hwnd, dc)
