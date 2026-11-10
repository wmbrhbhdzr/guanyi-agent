"""Screenshot review page; network/model work never touches Tk widgets."""

import io
import json
import queue
import math
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

from ..app.vision_service import VisionService
from ..vision.images import ImageInputError
from ..app.window_vision_service import WindowVisionService


class VisionPanel(ttk.Frame):
    def __init__(self, parent, service=None, window_service=None):
        super().__init__(parent, padding=10)
        self.service = service if service is not None else VisionService()
        self.window_service = window_service if window_service is not None else WindowVisionService(vision=self.service)
        self.windows = []
        self.selected_window = None
        self.continuous = False
        self._cycle_id = None
        self._cancel = threading.Event()
        self._last_hash = None
        self.path = None
        self.result = None
        self._preview = None
        self._queue = queue.Queue()
        self._poll_id = None
        self.busy = False
        self.path_var = tk.StringVar(value="尚未选择截图")
        self.status_var = tk.StringVar(value="先自动连接游戏或手动选择窗口；导入图片用于复测固定局面")
        self.game_var = tk.StringVar(value="自动（按标题）")
        connection = ttk.Frame(self)
        connection.pack(fill="x", pady=(0, 5))
        self.connect_button = ttk.Button(connection, text="自动连接游戏", command=lambda: self.refresh_windows(True))
        self.connect_button.pack(side="left")
        self.refresh_button = ttk.Button(connection, text="刷新窗口", command=self.refresh_windows)
        self.refresh_button.pack(side="left", padx=6)
        self.window_var = tk.StringVar()
        self.window_box = ttk.Combobox(connection, textvariable=self.window_var, state="readonly", width=70)
        self.window_box.pack(side="left", fill="x", expand=True)
        self.window_box.bind("<<ComboboxSelected>>", self.select_window)
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 5))
        self.capture_button = ttk.Button(actions, text="采集预览", command=lambda: self.capture_window(False))
        self.capture_button.pack(side="left")
        self.capture_run_button = ttk.Button(actions, text="采集并识别", command=lambda: self.capture_window(True))
        self.capture_run_button.pack(side="left", padx=6)
        ttk.Label(actions, text="间隔（秒）：").pack(side="left", padx=(8, 0))
        self.interval_var = tk.StringVar(value="5")
        self.interval_entry = ttk.Entry(actions, textvariable=self.interval_var, width=5)
        self.interval_entry.pack(side="left")
        self.start_button = ttk.Button(actions, text="开始连续识别", command=self.start_continuous)
        self.start_button.pack(side="left", padx=6)
        self.stop_button = ttk.Button(actions, text="暂停 / 停止", command=self.stop_continuous)
        self.stop_button.pack(side="left")
        top = ttk.Frame(self)
        top.pack(fill="x")
        self.choose_button = ttk.Button(top, text="导入测试图片", command=self.choose_image)
        self.choose_button.pack(side="left")
        self.run_button = ttk.Button(top, text="识别导入图片", command=self.recognize, state="disabled")
        self.run_button.pack(side="left", padx=8)
        self.game_box = ttk.Combobox(top, textvariable=self.game_var, state="readonly", width=14,
                                   values=["自动（按标题）", "通用识别", "杀戮尖塔2"])
        self.game_box.pack(side="left", padx=(0, 8))
        ttk.Label(top, textvariable=self.path_var, wraplength=650).pack(side="left", fill="x", expand=True)
        ttk.Label(self, text="仅采集所选窗口客户区；预览不请求模型。连续模式在本次完成后等待设定间隔，画面未变时跳过。",
                  foreground="#607D8B").pack(anchor="w", pady=(6, 2))
        ttk.Label(self, textvariable=self.status_var, foreground="#2F4B7C",
                  wraplength=980).pack(anchor="w", pady=4)
        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, pady=6)
        preview = ttk.LabelFrame(body, text="输入图片", padding=6)
        self.preview_label = ttk.Label(preview, text="请选择 PNG / JPEG / WebP / BMP 图片", anchor="center")
        self.preview_label.pack(fill="both", expand=True)
        body.add(preview, weight=1)
        results = ttk.Frame(body)
        body.add(results, weight=2)
        self.tabs = ttk.Notebook(results)
        self.tabs.pack(fill="both", expand=True)
        self.summary_text = self._text_tab("局面摘要")
        self.json_text = self._text_tab("完整结果")
        self.saved_var = tk.StringVar(value="识别记录会保存在 data/vision 中")
        ttk.Label(self, textvariable=self.saved_var, wraplength=980,
                  foreground="#607D8B").pack(anchor="w")
        self._controls()

    def _controls(self):
        idle = not self.busy and not self.continuous
        for button in (self.connect_button, self.refresh_button, self.choose_button):
            button.configure(state="normal" if idle else "disabled")
        self.window_box.configure(state="readonly" if idle else "disabled")
        self.game_box.configure(state="readonly" if idle else "disabled")
        self.interval_entry.configure(state="normal" if idle else "disabled")
        for button in (self.capture_button, self.capture_run_button, self.start_button):
            button.configure(state="normal" if idle and self.selected_window else "disabled")
        self.run_button.configure(state="normal" if idle and self.path else "disabled")
        self.stop_button.configure(state="normal" if self.continuous or self.busy else "disabled")

    def refresh_windows(self, auto=False):
        if self.busy or self.continuous:
            return
        self.selected_window = None
        self._last_hash = None
        try:
            self.windows = self.window_service.list_windows()
            self.window_box["values"] = [w.label for w in self.windows]
            supported = [w for w in self.windows if w.supported]
            self.window_var.set("")
            if auto and len(supported) == 1:
                self.window_var.set(supported[0].label)
                self.selected_window = supported[0]
                self.status_var.set("已连接：%s。可先采集预览，确认后识别。" % supported[0].title)
            elif auto:
                self.status_var.set("检测到多个游戏窗口，请手动选择" if supported else "未检测到已支持的游戏进程，请启动游戏或在列表中手动选择窗口")
            else:
                self.status_var.set("窗口列表已刷新，请选择游戏窗口")
        except Exception as exc:
            self.windows = []
            self.status_var.set("窗口检测失败：%s" % exc)
        self._controls()

    def select_window(self, _event=None):
        if self.busy or self.continuous:
            return
        self.selected_window = next((w for w in self.windows if w.label == self.window_var.get()), None)
        self._last_hash = None
        if self.selected_window:
            self.status_var.set("已选择：%s。只采集该窗口，不会读取游戏内存。" % self.selected_window.title)
        self._controls()

    def capture_window(self, recognize=True):
        if self.busy or self.selected_window is None:
            return
        self._cancel = threading.Event()
        cancel = self._cancel
        window = self.selected_window
        game = {"杀戮尖塔2": "sts2", "通用识别": "generic"}.get(self.game_var.get(), "auto")
        previous = self._last_hash if self.continuous and recognize else None
        self.busy = True
        self._controls()
        self.status_var.set("正在采集%s……" % window.title)
        def worker():
            try:
                result = self.window_service.run_once(window, game=game, recognize=recognize,
                                                     previous_hash=previous, cancel=cancel)
            except Exception:
                result = {"ok": False, "error": {"code": "capture_failed", "message": "采集未完成，请重新选择窗口"}}
            self._queue.put(result)
        threading.Thread(target=worker, daemon=True).start()
        self._poll_id = self.after(50, self._poll)

    def start_continuous(self):
        if self.busy or self.continuous or not self.selected_window:
            return
        try:
            interval = float(self.interval_var.get())
            if not math.isfinite(interval) or not 1 <= interval <= 300:
                raise ValueError()
        except ValueError:
            self.status_var.set("连续采集间隔应为1到300秒")
            return
        self._interval_ms = int(interval*1000)
        self.continuous = True
        self.capture_window(True)

    def stop_continuous(self):
        self.continuous = False
        self._cancel.set()
        if self._cycle_id is not None:
            self.after_cancel(self._cycle_id)
            self._cycle_id = None
        self.status_var.set("已停止后续采集；已发出的模型请求无法保证取消" if self.busy else "连续采集已停止，可重新开始")
        self._controls()

    def _schedule_next(self):
        if self.continuous:
            self._cycle_id = self.after(self._interval_ms, self._next_cycle)

    def _next_cycle(self):
        self._cycle_id = None
        if self.continuous:
            self.capture_window(True)

    def _preview_path(self, path):
        with Image.open(path) as source:
            picture = source.convert("RGB")
            picture.thumbnail((380, 400), Image.Resampling.LANCZOS)
            self._preview = ImageTk.PhotoImage(picture, master=self)
        self.preview_label.configure(image=self._preview, text="")

    def _text_tab(self, label):
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text=label)
        widget = tk.Text(frame, wrap="word", width=46, height=22, state="disabled")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=widget.yview)
        widget.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        widget.pack(fill="both", expand=True)
        return widget

    @staticmethod
    def _set_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def choose_image(self):
        path = filedialog.askopenfilename(parent=self, title="选择游戏截图",
                    filetypes=[("游戏截图", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")])
        if path:
            self.set_image(path)

    def set_image(self, path):
        """Load/preview locally; this operation does not call a model."""
        if self.busy:
            return False
        self.stop_continuous()
        self.path = None
        self.result = None
        self.run_button.configure(state="disabled")
        self._set_text(self.summary_text, "")
        self._set_text(self.json_text, "")
        self.saved_var.set("识别记录会保存在 data/vision 中")
        try:
            frame = self.service.prepare_image(path)
            with Image.open(io.BytesIO(frame.png)) as picture:
                picture.thumbnail((380, 460), Image.Resampling.LANCZOS)
                self._preview = ImageTk.PhotoImage(picture, master=self)
            self.preview_label.configure(image=self._preview, text="")
            self.path = str(path)
            self.path_var.set(str(path))
            self.status_var.set("图片已就绪（%d×%d），点击“识别截图”会请求模型" % frame.size)
            self.run_button.configure(state="normal")
            return True
        except (ImageInputError, OSError, ValueError) as exc:
            self._preview = None
            self.preview_label.configure(image="", text="无法读取图片")
            self.path_var.set("尚未选择有效截图")
            self.status_var.set(str(exc))
            return False

    def recognize(self):
        if self.busy or self.path is None:
            return
        self.busy = True
        self._cancel = threading.Event()
        self.result = None
        self.game_box.configure(state="disabled")
        self.choose_button.configure(state="disabled")
        self.run_button.configure(state="disabled")
        self._controls()
        self.status_var.set("正在识别……请稍候，界面可以正常切换")
        self._set_text(self.summary_text, "")
        self._set_text(self.json_text, "")
        path = self.path
        game = {"杀戮尖塔2": "sts2", "通用识别": "generic"}.get(self.game_var.get(), "auto")

        def worker():
            try:
                result = self.service.recognize(path, game=game)
            except Exception:
                result = {"ok": False, "error": {"code": "internal_error", "message": "识别未能完成，请检查图片或服务配置"}}
            self._queue.put(result)

        threading.Thread(target=worker, daemon=True).start()
        self._poll_id = self.after(50, self._poll)

    def _poll(self):
        self._poll_id = None
        try:
            result = self._queue.get_nowait()
        except queue.Empty:
            self._poll_id = self.after(50, self._poll)
            return
        self.result = result
        self.busy = False
        if self._cancel.is_set() or result.get("status") == "stopped":
            self.continuous = False
            self.status_var.set("已停止，未采用停止后返回的结果；可重新开始")
            self._controls()
            return
        if result.get("capture_path"):
            self._preview_path(result["capture_path"])
            self.path_var.set("窗口客户区：" + result.get("capture", {}).get("title", ""))
        if result.get("status") in ("captured", "unchanged"):
            self.status_var.set("采集预览完成，尚未请求模型" if result["status"] == "captured" else "窗口画面未变，已跳过本次模型调用")
            if result["status"] == "captured":
                self._set_text(self.summary_text, "这是当前窗口画面的本地预览，点击“采集并识别”读取局面。")
                self._set_text(self.json_text, "")
                self.saved_var.set("采集文件：" + result["capture_path"])
            self._controls()
            self._schedule_next()
            return
        if result.get("capture_hash") and result.get("ok"):
            self._last_hash = result["capture_hash"]
        if not result.get("ok"):
            self.continuous = False  # Do not repeatedly upload a failing frame.
        if result.get("ok"):
            self._set_text(self.summary_text, result["summary"])
            self._set_text(self.json_text, json.dumps(result["observation"], ensure_ascii=False, indent=2))
            label = {"recognized": "识别完成", "partial": "已提取部分内容，仍有信息待核对", "unrecognized": "未确认画面类型，请检查截图"}
            cost = (result.get("cost") or {}).get("cost_total_yuan", 0)
            profile = "杀戮尖塔2" if result.get("game_profile") == "sts2" else "通用识别"
            self.status_var.set("%s　适配：%s　耗时 %.0f ms　估算费用 %.4f 元；请对照图片核对" % (
                label.get(result.get("status"), "识别完成"), profile, result.get("elapsed_ms", 0), cost))
            if result.get("requested_profile") == "auto" and result.get("game_profile") == "generic":
                self.status_var.set(self.status_var.get() + "；标题未确认，可手动选择游戏")
        else:
            error = result.get("error") or {}
            text = error.get("message", "未能识别，请稍后重试")
            info = text + ("\n\n建议：" + error["action"] if error.get("action") else "")
            info += "\n\n错误类型：%s\n耗时：%.0f ms；尝试：%s；结束原因：%s" % (
                error.get("code", "unknown"), result.get("elapsed_ms", 0), result.get("attempts", "未知"),
                result.get("finish_reason", "未知"))
            self._set_text(self.summary_text, info)
            self._set_text(self.json_text, json.dumps({"error": error, "usage": result.get("usage"),
                "raw_response": result.get("raw_response"), "request_settings": result.get("request_settings")}, ensure_ascii=False, indent=2))
            self.status_var.set("识别未完成：%s（%s）" % (text, error.get("code", "unknown")))
        self.saved_var.set("运行记录：%s" % result["saved_path"] if result.get("saved_path")
                           else "本次结果未保存到文件")
        self._controls()
        self._schedule_next()

    def destroy(self):
        self.continuous = False
        self._cancel.set()
        if self._cycle_id is not None:
            self.after_cancel(self._cycle_id)
            self._cycle_id = None
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        super().destroy()
