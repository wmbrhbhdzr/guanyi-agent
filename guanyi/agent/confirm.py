# -*- coding: utf-8 -*-
"""人工确认（实验6 §2.5）：写操作执行前展示内容与影响，由用户明确同意后才执行。

三种实现：

- `CliConfirm`：命令行 y/N，**等待超时即视为拒绝**（不执行）；
- `GuiConfirm`：界面弹窗（带倒计时，超时视为拒绝）；
- `AutoApprove` / `AutoReject`：测试与无人值守演示用。

统一返回：`{"approved": bool, "reason": str, "how": "cli"/"gui"/"auto"/"timeout"}`。
"""

import queue
import threading
import time
from typing import Dict, Optional
from .runtime import wait_call


class ConfirmBase:
    def confirm(self, request: Dict) -> Dict:
        raise NotImplementedError

    def confirm_with_timeout(self, request: Dict, timeout_s: float) -> Dict:
        return wait_call(lambda: self.confirm(request), timeout_s)


class AutoApprove(ConfirmBase):
    """自动同意（`--yes` 与测试用）：仍会在日志里留痕。"""

    def confirm(self, request: Dict) -> Dict:
        return {"approved": True, "reason": "自动同意（--yes / 测试桩）", "how": "auto"}


class AutoReject(ConfirmBase):
    """自动拒绝（测试用）。"""

    def confirm(self, request: Dict) -> Dict:
        return {"approved": False, "reason": "自动拒绝（测试桩）", "how": "auto"}


class CliConfirm(ConfirmBase):
    """命令行确认：y/N，超时未回答视为拒绝。"""

    def __init__(self, timeout_s: float = 30.0, stream=None):
        self.timeout_s = timeout_s
        self.stream = stream
        self._print = (stream.write if stream is not None else print)

    def confirm(self, request: Dict) -> Dict:
        self._print("\n【需要确认】%s" % request.get("title", "写操作"))
        for line in request.get("lines", []):
            self._print("  - %s" % line)
        self._print("  影响：%s" % request.get("impact", "未知"))
        self._print("  等待确认最多 %.0f 秒；仅 y/yes/是/确认表示同意，其余输入或超时视为拒绝。" % self.timeout_s)

        box: "queue.Queue[str]" = queue.Queue()

        def _read():
            try:
                box.put(input("确认执行？[y/N] ").strip().lower())
            except (EOFError, KeyboardInterrupt):
                box.put("")

        threading.Thread(target=_read, daemon=True).start()
        self._flush()
        try:
            answer = box.get(timeout=self.timeout_s)
        except queue.Empty:
            self._print("  → 等待超时，操作未执行。")
            return {"approved": False, "reason": "等待确认超时（%.0f 秒）" % self.timeout_s,
                    "how": "timeout"}
        approved = answer in ("y", "yes", "是", "确认")
        self._print("  → %s" % ("用户同意，继续执行" if approved else "用户拒绝，操作未执行"))
        return {"approved": approved, "reason": "用户同意" if approved else "用户拒绝",
                "how": "cli"}

    def _flush(self):
        try:
            import sys
            sys.stdout.flush()
        except Exception:                              # noqa: BLE001
            pass


class GuiConfirm(ConfirmBase):
    """界面确认：弹窗 + 倒计时，超时视为拒绝。"""

    def __init__(self, parent=None, timeout_s: float = 30.0):
        self.parent = parent
        self.timeout_s = timeout_s

    def confirm_with_timeout(self, request: Dict, timeout_s: float) -> Dict:
        # Tk 控件只能在调用者的 GUI 线程创建。
        original = self.timeout_s
        self.timeout_s = min(original, max(0, timeout_s))
        try:
            return self.confirm(request)
        finally:
            self.timeout_s = original

    def confirm(self, request: Dict) -> Dict:
        import tkinter as tk

        text = "%s\n\n%s\n\n影响：%s\n\n最多等待 %.0f 秒，超时视为拒绝。" % (
            request.get("title", "写操作"),
            "\n".join("· " + line for line in request.get("lines", [])),
            request.get("impact", "未知"), self.timeout_s)
        if self.parent is None:
            raise ValueError("GuiConfirm 需要 GUI 父窗口以执行倒计时")

        win = tk.Toplevel(self.parent)
        win.title("观弈：需要确认")
        win.transient(self.parent)
        win.grab_set()
        tk.Label(win, text=text, justify="left", wraplength=460, padx=14, pady=10).pack()
        state = {"approved": False, "how": "timeout"}
        deadline = time.monotonic() + self.timeout_s
        countdown = {"left": max(0, int(self.timeout_s))}
        label = tk.Label(win, text="剩余 %d 秒" % countdown["left"], fg="#B26A00")
        label.pack()

        def finish(approved: bool, how: str):
            state["approved"] = approved
            state["how"] = how
            try:
                win.destroy()
            except Exception:                          # noqa: BLE001
                pass

        def tick():
            if not win.winfo_exists():
                return
            remaining = deadline - time.monotonic()
            countdown["left"] = max(0, int(remaining + 0.999))
            if remaining <= 0:
                finish(False, "timeout")
                return
            label.config(text="剩余 %d 秒" % countdown["left"])
            win.after(min(1000, max(1, int(remaining * 1000))), tick)

        buttons = tk.Frame(win)
        buttons.pack(pady=8)
        tk.Button(buttons, text="同意执行", width=12,
                  command=lambda: finish(True, "gui")).pack(side="left", padx=6)
        tk.Button(buttons, text="拒绝", width=12,
                  command=lambda: finish(False, "gui")).pack(side="left", padx=6)
        win.protocol("WM_DELETE_WINDOW", lambda: finish(False, "gui"))
        win.after(max(1, min(1000, int(self.timeout_s * 1000))), tick)
        try:
            self.parent.wait_window(win)               # 阻塞到窗口关闭
        except Exception:                              # noqa: BLE001
            pass
        reason = "用户同意" if state["approved"] else (
            "等待确认超时（%.0f 秒）" % self.timeout_s if state["how"] == "timeout" else "用户拒绝")
        return {"approved": state["approved"], "reason": reason, "how": state["how"]}
