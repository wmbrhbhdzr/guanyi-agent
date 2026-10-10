# -*- coding: utf-8 -*-
"""界面层：Tkinter 三个页面（对应实验3 图 8 的页面结构与导航图）。

    · 核心任务页：录入局面与操作 → 规则基线建议 → 护栏结论 → 落盘
    · 记录列表页：对局选择 + 决策点表格（含空数据与损坏行提示）
    · 复盘报告页：生成并展示逐回合复盘报告

设计要点（沿用实验3 的约束）：

1. 界面层只调用应用层服务，不直接读写文件；
2. 所有异常都转成中文提示（`zh_message`），程序不崩、不打印堆栈；
3. “仅复盘”档不介入游玩：这里只做记录与复盘，玩家操作由自己填。

启动：`python -m guanyi.ui`
"""

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


def _ensure_tcl_env():
    """Windows 上从虚拟环境启动 Tk 时，Tcl/Tk 的库目录可能找不到。

    现象是 `_tkinter.TclError: Can't find a usable init.tcl`——因为 venv 的
    `sys.prefix` 指向虚拟环境，而 Tcl 库在基础解释器的 `tcl/` 目录下。
    这里按需把 `TCL_LIBRARY`／`TK_LIBRARY` 补成基础解释器的路径，
    让「双击就能跑」成立（否则每次都要手动设环境变量）。
    """
    if sys.platform != "win32" or os.environ.get("TCL_LIBRARY"):
        return
    base = getattr(sys, "base_prefix", sys.prefix)
    for name, sub in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
        path = os.path.join(base, "tcl", sub)
        if os.path.isdir(path):
            os.environ[name] = path


_ensure_tcl_env()

from ..app.service import SessionService
from ..core.actions import action_key
from ..core.errors import GuanyiError, zh_message
from ..data.store import JsonlStore

#: 实验4 只用最基础的几张牌，后续实验会改为从截图识别
CARDS = ["防御", "打击", "重击", "痛击", "铁斩波"]


class GuanyiApp(tk.Tk):
    """观弈主窗口。"""

    def __init__(self, service=None):
        super().__init__()
        self.service = service or SessionService(JsonlStore())
        self.title("观弈 GuanYi · 仅复盘模式（实验4 非 AI 版本）")
        self.geometry("1080x720")
        self.minsize(940, 620)

        self.run_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪：请先新建或选择一局对局")
        self.suggestion_text = tk.StringVar(value="（还没给出建议）")
        self.guardrail_text = tk.StringVar(value="（还没有护栏结论）")
        self.report_path_var = tk.StringVar(value="")
        self.problems_var = tk.StringVar(value="")

        self._build_toolbar()
        self._build_pages()
        self._build_statusbar()
        self.refresh_runs()
        self.refresh_summary()          # 打开就有摘要，不用先点按钮
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ---------------- 顶部工具条 ----------------
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="当前对局：").pack(side="left")
        self.run_box = ttk.Combobox(bar, textvariable=self.run_var, width=24, state="readonly")
        self.run_box.pack(side="left", padx=(0, 8))
        self.run_box.bind("<<ComboboxSelected>>", lambda _e: self.on_select_run())
        ttk.Button(bar, text="新建对局", command=self.on_new_run).pack(side="left", padx=2)
        ttk.Button(bar, text="刷新", command=self.refresh_runs).pack(side="left", padx=2)
        ttk.Label(bar, text="档位：仅复盘　·　决策来源：规则基线（非 AI）",
                  foreground="#2F4B7C").pack(side="right")

    # ---------------- 三个页面 ----------------
    def _build_pages(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.tab_task = ttk.Frame(self.nb, padding=10)
        self.tab_list = ttk.Frame(self.nb, padding=10)
        self.tab_report = ttk.Frame(self.nb, padding=10)
        self.nb.add(self.tab_task, text="核心任务页")
        self.nb.add(self.tab_list, text="记录列表")
        self.nb.add(self.tab_report, text="复盘报告")
        self._build_task_tab()
        self._build_list_tab()
        self._build_report_tab()

    def _build_task_tab(self):
        left = ttk.LabelFrame(self.tab_task, text="① 局面（你来填）", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.tab_task.columnconfigure(0, weight=1)
        self.tab_task.columnconfigure(1, weight=1)
        self.tab_task.columnconfigure(2, weight=1)

        self.entries = {}
        for row, (key, label, default) in enumerate([
            ("hp", "当前血量", "42"), ("max_hp", "最大血量", "80"), ("energy", "本回合能量", "3"),
            ("enemy_hp", "敌人血量", "23"), ("enemy_intent", "敌人意图伤害", "11"),
        ]):
            ttk.Label(left, text=label).grid(row=row, column=0, sticky="w", pady=3)
            entry = ttk.Entry(left, width=10)
            entry.insert(0, default)
            entry.grid(row=row, column=1, sticky="w", pady=3)
            self.entries[key] = entry

        ttk.Label(left, text="回合数").grid(row=5, column=0, sticky="w", pady=3)
        self.entries["turn"] = ttk.Entry(left, width=10)
        self.entries["turn"].insert(0, "1")
        self.entries["turn"].grid(row=5, column=1, sticky="w", pady=3)

        ttk.Label(left, text="手牌（可多选）").grid(row=6, column=0, sticky="nw", pady=(8, 3))
        self.hand_box = tk.Listbox(left, selectmode="extended", height=5, exportselection=False)
        for card in CARDS:
            self.hand_box.insert("end", card)
        self.hand_box.grid(row=6, column=1, sticky="w", pady=(8, 3))
        self.hand_box.selection_set(0, 1)

        # 输入一改就刷新摘要：避免“摘要”与真实输入自相矛盾（测试发现的缺陷）
        for entry in self.entries.values():
            entry.bind("<KeyRelease>", lambda _e: self.refresh_summary())
            entry.bind("<FocusOut>", lambda _e: self.refresh_summary())
        self.hand_box.bind("<<ListboxSelect>>", lambda _e: self.refresh_summary())

        ttk.Label(left, text="局面摘要（由上面的数字自动生成，避免与实际输入不一致）").grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(10, 3))
        self.state_entry = ttk.Entry(left, width=46, state="readonly")
        self.state_entry.grid(row=8, column=0, columnspan=2, sticky="we")
        ttk.Button(left, text="按上面的数字重新生成摘要",
                   command=self.on_fill_summary).grid(row=9, column=0, columnspan=2,
                                                      sticky="w", pady=(6, 0))

        mid = ttk.LabelFrame(self.tab_task, text="② 建议（规则基线，非 AI）", padding=10)
        mid.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        ttk.Button(mid, text="让规则基线给建议", command=self.on_suggest).pack(anchor="w")
        ttk.Label(mid, textvariable=self.suggestion_text, wraplength=260,
                  justify="left", foreground="#2F4B7C").pack(anchor="w", pady=(8, 12))
        ttk.Separator(mid).pack(fill="x")
        ttk.Label(mid, text="③ 护栏结论", padding=(0, 8, 0, 4)).pack(anchor="w")
        ttk.Label(mid, textvariable=self.guardrail_text, wraplength=260,
                  justify="left", foreground="#B26A00").pack(anchor="w")

        right = ttk.LabelFrame(self.tab_task, text="④ 我实际怎么打", padding=10)
        right.grid(row=0, column=2, sticky="nsew")
        ttk.Label(right, text="打出的牌").pack(anchor="w")
        self.play_card = ttk.Combobox(right, values=CARDS, width=16, state="readonly")
        self.play_card.set("打击")
        self.play_card.pack(anchor="w", pady=(0, 8))
        self.end_turn_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(right, text="这一手我结束回合", variable=self.end_turn_var).pack(anchor="w")
        ttk.Label(right, text="本回合结果（可留空）").pack(anchor="w", pady=(12, 2))
        ttk.Label(right, text="血量变化").pack(anchor="w")
        self.hp_delta = ttk.Entry(right, width=10)
        self.hp_delta.insert(0, "-11")
        self.hp_delta.pack(anchor="w")
        ttk.Label(right, text="敌方血量变化").pack(anchor="w", pady=(6, 2))
        self.enemy_delta = ttk.Entry(right, width=10)
        self.enemy_delta.insert(0, "-6")
        self.enemy_delta.pack(anchor="w")
        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Button(right, text="采用建议并记录", command=lambda: self.on_record(use_suggestion=True)
                   ).pack(fill="x", pady=3)
        ttk.Button(right, text="按我的操作记录", command=lambda: self.on_record(use_suggestion=False)
                   ).pack(fill="x", pady=3)
        ttk.Label(right, text="决策权在你：两个按钮都会如实记录，\n只有“采用建议”才把建议当成你的操作。",
                  foreground="#607D8B", justify="left").pack(anchor="w", pady=(8, 0))

    def _build_list_tab(self):
        top = ttk.Frame(self.tab_list)
        top.pack(fill="x")
        ttk.Button(top, text="刷新记录", command=self.refresh_list).pack(side="left")
        ttk.Label(top, textvariable=self.problems_var, foreground="#D32F2F").pack(side="left", padx=12)
        columns = ("turn", "state", "suggest", "play", "consistent", "guardrail", "result")
        self.tree = ttk.Treeview(self.tab_list, columns=columns, show="headings", height=16)
        for col, text, width in [
            ("turn", "回合", 50), ("state", "局面摘要", 300), ("suggest", "建议", 110),
            ("play", "你的操作", 110), ("consistent", "是否一致", 70),
            ("guardrail", "护栏", 90), ("result", "结果", 160),
        ]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=8)

    def _build_report_tab(self):
        top = ttk.Frame(self.tab_report)
        top.pack(fill="x")
        ttk.Button(top, text="生成复盘报告", command=self.on_report).pack(side="left")
        ttk.Label(top, textvariable=self.report_path_var, foreground="#2E7D32").pack(side="left", padx=12)
        self.report_text = tk.Text(self.tab_report, wrap="word", height=26)
        self.report_text.pack(fill="both", expand=True, pady=8)

    def _build_statusbar(self):
        bar = ttk.Frame(self, padding=(10, 6))
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.status_var, foreground="#37474F").pack(side="left")

    # ---------------- 数据与动作 ----------------
    def _fail(self, exc):
        """统一的错误提示：中文说明 + 错误码，绝不让程序崩掉。"""
        if isinstance(exc, GuanyiError):
            text = "%s（%s）\n%s" % (exc.message, exc.code, zh_message(exc.code))
        else:
            text = "程序内部错误：%s" % exc
        self.status_var.set("✗ " + text.splitlines()[0])
        messagebox.showwarning("观弈：操作未完成", text)

    def refresh_runs(self):
        runs = self.service.list_runs()
        ids = [r["run_id"] for r in runs]
        self.run_box["values"] = ids
        if ids and self.run_var.get() not in ids:
            self.run_var.set(ids[-1])
        self.status_var.set("共 %d 局记录%s" % (len(ids), "" if ids else "：还没有对局，点“新建对局”开始"))
        if self.run_var.get():
            self.refresh_list()

    def on_new_run(self):
        try:
            run = self.service.start_run(seed="UI")
        except Exception as exc:                     # noqa: BLE001 — 界面兜底
            return self._fail(exc)
        self.refresh_runs()
        self.run_var.set(run.run_id)
        self.status_var.set("已新建对局 %s（还没有决策点）" % run.run_id)
        self.refresh_list()

    def on_select_run(self):
        self.refresh_summary()
        self.refresh_list()
        self.status_var.set("切换到对局 %s" % self.run_var.get())

    def current_run(self):
        run_id = self.run_var.get()
        if not run_id:
            raise GuanyiError("请先新建或选择一局对局")
        return run_id

    def read_int(self, key, default=0):
        raw = self.entries[key].get().strip()
        if raw == "":
            return default
        return int(raw)                                # 非法输入 → ValueError，由 _fail 兜底

    def read_state(self):
        hand = [self.hand_box.get(i) for i in self.hand_box.curselection()]
        return {
            "hp": self.read_int("hp"), "max_hp": self.read_int("max_hp", 80),
            "energy": self.read_int("energy", 3),
            "enemy_hp": self.read_int("enemy_hp"), "enemy_intent": self.read_int("enemy_intent"),
            "hand": hand,
        }

    def build_summary(self, state):
        """由结构化局面生成人类可读的摘要（保证摘要与实际输入永远一致）。"""
        return ("HP %d/%d，能量 %d，敌人 HP %d 意图攻击 %d，手牌 %s"
                % (state["hp"], state["max_hp"], state["energy"], state["enemy_hp"],
                   state["enemy_intent"], "／".join(state["hand"]) or "空"))

    def refresh_summary(self, silent=True):
        """把摘要刷成与当前输入一致。

        `silent=True` 用于输入过程中的自动刷新：数字还没填完时静默跳过，
        不弹提示框（否则每按一个键都可能弹窗）。
        """
        try:
            state = self.read_state()
        except ValueError as exc:
            if silent:
                return
            return self._fail(GuanyiError("血量、能量、意图等必须是整数：%s" % exc))
        self.state_entry.configure(state="normal")
        self.state_entry.delete(0, "end")
        self.state_entry.insert(0, self.build_summary(state))
        self.state_entry.configure(state="readonly")

    def on_fill_summary(self):
        self.refresh_summary(silent=False)

    def on_suggest(self):
        try:
            state = self.read_state()
            legal = ["play_card:%s" % c for c in state["hand"]] + ["end_turn"]
            result = self.service.suggest(state, legal)
        except Exception as exc:                       # noqa: BLE001
            return self._fail(exc)
        action = result["action"]
        self.suggestion_text.set("建议：%s\n依据：%s\n置信度：%.2f"
                                 % (action_key(action) or "无法给出建议",
                                    result["reason"], result["confidence"]))
        self.guardrail_text.set("（护栏结论会在记录时给出）")
        self.status_var.set("规则基线已给出建议")

    def on_record(self, use_suggestion):
        try:
            run_id = self.current_run()
            state = self.read_state()
            legal = ["play_card:%s" % c for c in state["hand"]] + ["end_turn"]
            summary = self.build_summary(state)     # 摘要一律由输入生成，避免自相矛盾
            if self.end_turn_var.get():
                player_action = {"action_type": "end_turn"}
            else:
                player_action = {"action_type": "play_card", "card_name": self.play_card.get(),
                                 "energy_cost": 1}
            result = {}
            if self.hp_delta.get().strip():
                result["hp_delta"] = int(self.hp_delta.get().strip())
            if self.enemy_delta.get().strip():
                result["enemy_delta"] = int(self.enemy_delta.get().strip())

            suggestion = None
            if use_suggestion:
                suggestion = self.service.suggest(state, legal)["action"]

            point = self.service.record_decision(
                run_id=run_id, turn=self.read_int("turn", 1), state_summary=summary,
                suggestion_action=suggestion, player_action=player_action, state=state,
                result=result, legal_actions=legal)
        except Exception as exc:                       # noqa: BLE001
            return self._fail(exc)

        verdict = point.guardrail
        self.guardrail_text.set("%s：%s" % (verdict.get("verdict"), verdict.get("reason")))
        warn = "" if verdict.get("verdict") == "allow" else "　⚠ 护栏已拦截（以规则为准）"
        self.status_var.set("已记录第 %d 回合：建议 %s ／ 实际 %s　一致=%s%s"
                            % (point.turn, action_key(point.suggestion_action),
                               action_key(point.player_action), "是" if point.is_consistent else "否", warn))
        self.entries["turn"].delete(0, "end")
        self.entries["turn"].insert(0, str(point.turn + 1))
        self.refresh_summary()
        self.refresh_list()

    def refresh_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        run_id = self.run_var.get()
        if not run_id:
            self.problems_var.set("")
            return
        try:
            points, problems = self.service.scan_decisions(run_id)
        except Exception as exc:                       # noqa: BLE001
            self.problems_var.set("读取失败：%s" % getattr(exc, "message", exc))
            return
        if not points:
            self.tree.insert("", "end", values=("—", "本局还没有决策点（空数据）", "—", "—",
                                                "—", "—", "—"))
        for p in points:
            self.tree.insert("", "end", values=(
                p.turn, p.state_summary, action_key(p.suggestion_action) or "—",
                action_key(p.player_action) or "—", "✓" if p.is_consistent else "✗",
                p.guardrail.get("verdict", "—"),
                "；".join("%s=%s" % kv for kv in p.result.items()) or "—"))
        self.problems_var.set("⚠ %d 行记录损坏已跳过（行号：%s）"
                              % (len(problems), "、".join(str(x["line"]) for x in problems))
                              if problems else "")

    def on_report(self):
        try:
            run_id = self.current_run()
            result = self.service.build_report(run_id)
            text = Path(result["path"]).read_text(encoding="utf-8")   # 用上下文管理，避免句柄泄漏
        except OSError as exc:
            return self._fail(GuanyiError("读取报告文件失败：%s" % exc))
        except Exception as exc:                       # noqa: BLE001
            return self._fail(exc)
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", text)
        self.report_path_var.set("已生成：%s（决策点 %d 个）"
                                 % (result["path"], result["summary"]["decision_count"]))
        self.status_var.set("复盘报告已生成，可在“复盘报告”页阅读或导出")
        self.nb.select(self.tab_report)


def main():
    app = GuanyiApp()
    app.mainloop()


if __name__ == "__main__":
    main()
