# -*- coding: utf-8 -*-
"""界面冒烟测试：不靠人工点击，用程序把三个页面驱动跑通一遍。

做这些事：新建对局 → 生成局面摘要 → 规则基线给建议 → 记录两笔（第 2 笔建议与实际不一致）
→ 读记录列表 → 生成复盘报告，并打印每一步的界面状态文本。

同时把弹出的提示框替换成打印，避免无人值守时被对话框卡住。

用法：`.venv\\Scripts\\python.exe scripts\\ui_smoke.py`
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:                                                      # 控制台是 GBK 时也能打印 ✓ ✗
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                         # noqa: BLE001
    pass

import tkinter.messagebox as messagebox  # noqa: E402

from guanyi.app.service import SessionService  # noqa: E402
from guanyi.data.store import JsonlStore  # noqa: E402
from guanyi.ui.main_window import GuanyiApp  # noqa: E402

ROOT = "data/_ui_smoke"


def main():
    # 无人值守：对话框改为打印
    messagebox.showwarning = lambda title, msg, **kw: print("[提示框] %s / %s" % (title, msg.replace("\n", " ")))
    messagebox.showerror = lambda title, msg, **kw: print("[错误框] %s / %s" % (title, msg.replace("\n", " ")))

    shutil.rmtree(ROOT, ignore_errors=True)
    service = SessionService(JsonlStore(os.path.join(ROOT, "runs")))
    app = GuanyiApp(service)
    app.update()

    app.on_new_run()
    app.update()
    print("① 新建对局：%s" % app.run_var.get())
    print("   状态栏：%s" % app.status_var.get())

    app.on_fill_summary()
    app.update()
    print("② 局面摘要：%s" % app.state_entry.get())

    app.on_suggest()
    app.update()
    print("③ 规则基线建议：%s" % app.suggestion_text.get().replace("\n", " ｜ "))

    app.on_record(use_suggestion=True)
    app.update()
    print("④ 采用建议并记录 → %s" % app.status_var.get())
    print("   护栏结论：%s" % app.guardrail_text.get())

    # 第二笔：把敌人意图调高，让基线的保血分支生效；玩家却打出攻击 → 不一致
    app.entries["enemy_intent"].delete(0, "end")
    app.entries["enemy_intent"].insert(0, "30")
    app.play_card.set("打击")
    app.on_record(use_suggestion=False)
    app.update()
    print("⑤ 按我的操作记录 → %s" % app.status_var.get())

    app.refresh_list()
    app.update()
    rows = app.tree.get_children()
    print("⑥ 记录列表：%d 行" % len(rows))
    for item in rows:
        print("   %s" % " ｜ ".join(str(v) for v in app.tree.item(item, "values")))

    app.on_report()
    app.update()
    print("⑦ 复盘报告：%s" % app.report_path_var.get())
    head = app.report_text.get("1.0", "end").strip().splitlines()
    print("   报告前 12 行：")
    for line in head[:12]:
        print("   %s" % line)

    app.destroy()
    print("\n界面冒烟测试完成：三个页面均可驱动，无异常抛出。")


if __name__ == "__main__":
    main()
