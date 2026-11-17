"""Warm neutral desktop theme, with moss and terracotta accents."""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

COLORS = {
    "background": "#F3F0E9", "surface": "#FFFDF8", "ink": "#302F29",
    "muted": "#767368", "border": "#DAD5C9", "accent": "#49634C",
    "accent_hover": "#354D38", "soft": "#E6EBDD", "clay": "#A45E42",
    "disabled": "#A49E91", "selected": "#DCE6D7",
}


def install_theme(root):
    c = COLORS
    root.configure(background=c["background"])
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name, root=root).configure(family="Microsoft YaHei UI", size=-14)
    root.option_add("*TCombobox*Listbox.background", c["surface"])
    root.option_add("*TCombobox*Listbox.foreground", c["ink"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["selected"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["ink"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=c["background"], foreground=c["ink"],
                    font=("Microsoft YaHei UI", -14), bordercolor=c["border"],
                    lightcolor=c["surface"], darkcolor=c["border"], focuscolor=c["accent"])
    style.configure("TFrame", background=c["background"])
    style.configure("TLabel", background=c["background"], foreground=c["ink"])
    style.configure("Muted.TLabel", foreground=c["muted"])
    style.configure("Brand.TLabel", font=("Microsoft YaHei UI", -30, "bold"))
    style.configure("Eyebrow.TLabel", foreground=c["accent"], font=("Segoe UI", -11, "bold"))
    style.configure("PageTitle.TLabel", font=("Microsoft YaHei UI", -23, "bold"))
    style.configure("Badge.TLabel", background=c["soft"], foreground=c["accent"], padding=(12, 7))
    style.configure("TButton", background=c["surface"], foreground=c["ink"],
                    padding=(12, 7), borderwidth=1, relief="flat")
    style.map("TButton", background=[("disabled", c["background"]), ("pressed", c["selected"]),
                                     ("active", c["soft"])], foreground=[("disabled", c["disabled"])])
    style.configure("Primary.TButton", background=c["accent"], foreground="#FFFDF8", bordercolor=c["accent"])
    style.map("Primary.TButton", background=[("disabled", "#DCDDD2"), ("active", c["accent_hover"])],
              foreground=[("disabled", c["muted"]), ("!disabled", "#FFFDF8")])
    style.configure("Stop.TButton", foreground=c["clay"])
    style.configure("TEntry", fieldbackground=c["surface"], padding=(7, 6), insertcolor=c["ink"])
    style.configure("TCombobox", fieldbackground=c["surface"], background=c["surface"],
                    arrowcolor=c["accent"], padding=(7, 6))
    style.map("TCombobox", fieldbackground=[("readonly", c["surface"]), ("disabled", c["background"])],
              selectbackground=[("readonly", c["surface"])], selectforeground=[("readonly", c["ink"])])
    style.configure("TLabelframe", bordercolor=c["border"], borderwidth=1, relief="solid")
    style.configure("TLabelframe.Label", foreground=c["accent"], font=("Microsoft YaHei UI", -14, "bold"))
    style.configure("TNotebook", borderwidth=0, tabmargins=(0, 4, 0, 12), background=c["background"])
    style.configure("TNotebook.Tab", padding=(18, 10), background=c["background"], foreground=c["muted"])
    style.map("TNotebook.Tab", background=[("selected", c["surface"]), ("active", c["soft"])],
              foreground=[("selected", c["accent"]), ("active", c["ink"])])
    style.configure("Treeview", background=c["surface"], fieldbackground=c["surface"],
                    foreground=c["ink"], rowheight=36, borderwidth=0)
    style.configure("Treeview.Heading", background=c["soft"], foreground=c["accent"],
                    padding=(10, 10), font=("Microsoft YaHei UI", -14, "bold"))
    style.map("Treeview", background=[("selected", c["selected"])], foreground=[("selected", c["ink"])])
    style.configure("TPanedwindow", background=c["border"])
    style.configure("Vertical.TScrollbar", background=c["border"], troughcolor=c["background"],
                    arrowcolor=c["muted"], borderwidth=0, arrowsize=12)
    return style


def polish_classic_widgets(parent):
    """Style Tk text/list widgets that do not inherit ttk colors."""
    c = COLORS
    if isinstance(parent, (tk.Text, tk.Listbox)):
        parent.configure(background=c["surface"], foreground=c["ink"],
                         selectbackground=c["selected"], selectforeground=c["ink"],
                         relief="flat", borderwidth=0, highlightthickness=1,
                         highlightbackground=c["border"], highlightcolor=c["accent"])
        if isinstance(parent, tk.Text):
            family = tkfont.Font(root=parent, font=parent.cget("font")).actual("family")
            font = ("Consolas", -13) if family.lower() == "consolas" else ("Microsoft YaHei UI", -14)
            parent.configure(font=font, padx=14, pady=12, spacing1=3, spacing3=6, insertbackground=c["ink"])
    for child in parent.winfo_children():
        polish_classic_widgets(child)


def page_heading(parent, title, description):
    frame = ttk.Frame(parent)
    frame.pack(fill="x", pady=(0, 16))
    ttk.Label(frame, text=title, style="PageTitle.TLabel").pack(anchor="w")
    ttk.Label(frame, text=description, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
