# -*- coding: utf-8 -*-
"""生成实验6 报告用的「Agent 循环图」（讲义 2.3 要求）。

    python scripts/draw_exp6_agent_loop.py

输出：image/实验6-工具调用、Agent与Harness实现/图1-Agent循环图.png

画的是“接收目标 → 模型提出调用请求 → 程序检查并执行工具 → 回传工具结果 → 模型继续 / 最终回答”
这条循环，并在图上标出 **参数校验、人工确认、停止检查** 三个位置。
"""

import math
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("需要 Pillow（实验1 已安装）")
    sys.exit(2)

W, H = 1400, 1060
BG = (250, 251, 253)
INK = (28, 32, 38)
MUTED = (95, 104, 118)
MAIN = ((233, 240, 250), (44, 72, 122))
CHECK = ((255, 247, 228), (176, 104, 0))
CONFIRM = ((253, 235, 235), (178, 30, 30))
END = ((233, 245, 234), (43, 120, 48))

FONTS = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
         r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc"]
_cache = {}


def font(size, bold=False):
    key = (size, bold)
    if key in _cache:
        return _cache[key]
    paths = ([r"C:\Windows\Fonts\msyhbd.ttc"] if bold else []) + FONTS
    for path in paths:
        if os.path.exists(path):
            try:
                _cache[key] = ImageFont.truetype(path, size)
                return _cache[key]
            except Exception:                            # noqa: BLE001
                continue
    _cache[key] = ImageFont.load_default()
    return _cache[key]


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
f_title, f_sub = font(25, True), font(14)
f_box, f_tag, f_note = font(16), font(12, True), font(13)


def box(x, y, w, h, lines, style=MAIN, tag=None, bold=False):
    fill, edge = style
    d.rounded_rectangle([x, y, x + w, y + h], radius=9, fill=fill, outline=edge, width=2)
    if isinstance(lines, str):
        lines = [lines]
    lh = 21
    start = y + (h - lh * len(lines)) / 2 + 1
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=font(16, bold))
        d.text((x + (w - tw) / 2, start + i * lh), line, font=font(16, bold), fill=INK)
    if tag:
        tw = d.textlength(tag, font=f_tag)
        d.rounded_rectangle([x + w - tw - 16, y - 10, x + w + 6, y + 8], radius=6, fill=edge)
        d.text((x + w - tw - 5, y - 9), tag, font=f_tag, fill=(255, 255, 255))


def arrow(pts, label=None, dashed=False, label_at=0.5):
    """画折线箭头；pts 为点列表。"""
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        if dashed:
            total = math.hypot(x2 - x1, y2 - y1)
            n = max(int(total // 9), 1)
            for k in range(0, n, 2):
                t1, t2 = k / n, min((k + 1) / n, 1)
                d.line([x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1,
                        x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2], fill=MUTED, width=2)
        else:
            d.line([x1, y1, x2, y2], fill=MUTED, width=2)
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    ang = math.atan2(y2 - y1, x2 - x1)
    size = 11
    d.polygon([(x2, y2),
               (x2 - size * math.cos(ang - 0.38), y2 - size * math.sin(ang - 0.38)),
               (x2 - size * math.cos(ang + 0.38), y2 - size * math.sin(ang + 0.38))], fill=MUTED)
    if label:
        idx = max(0, min(int((len(pts) - 1) * label_at), len(pts) - 2))
        (ax, ay), (bx, by) = pts[idx], pts[idx + 1]
        mx, my = (ax + bx) / 2, (ay + by) / 2
        tw = d.textlength(label, font=f_note)
        d.rectangle([mx - tw / 2 - 5, my - 11, mx + tw / 2 + 5, my + 11], fill=BG)
        d.text((mx - tw / 2, my - 9), label, font=f_note, fill=MUTED)


# ---------- 标题 ----------
title = "观弈 · 复盘分析 Agent 循环（单 Agent + 运行时 Harness）"
d.text(((W - d.textlength(title, font=f_title)) / 2, 20), title, font=f_title, fill=INK)
sub = "分工：模型决定“调哪个工具、什么时候收尾”；程序决定“能不能调、要不要确认、什么时候停”"
d.text(((W - d.textlength(sub, font=f_sub)) / 2, 54), sub, font=f_sub, fill=MUTED)

MX, MW = 470, 520          # 主流程框
LX, LW = 30, 380           # 左侧旁注
RX, RW = 1050, 330         # 右侧终点分支
Y = [96, 176, 256, 336, 416, 496, 576, 656, 736]
H_BOX = 58

# ---------- 主流程 ----------
box(MX, Y[0], MW, H_BOX, "① 接收任务目标（自然语言）")
arrow([(MX + MW / 2, Y[0] + H_BOX), (MX + MW / 2, Y[1])])

box(MX, Y[1], MW, H_BOX, ["② Harness 初始化：任务编号 / 限制 / 日志 / 工具白名单"])
arrow([(MX + MW / 2, Y[1] + H_BOX), (MX + MW / 2, Y[2])])

box(MX, Y[2], MW, H_BOX, ["③ 停止检查（程序）", "步数 ≥ 上限？耗时 ≥ 总时限？"],
    style=CHECK, tag="停止检查")
arrow([(MX + MW / 2, Y[2] + H_BOX), (MX + MW / 2, Y[3])], "未超限")

box(MX, Y[3], MW, H_BOX, ["④ 调用模型（附带 tools Schema）", "→ 返回 tool_calls 或最终回答"])
arrow([(MX + MW / 2, Y[3] + H_BOX), (MX + MW / 2, Y[4])])

box(MX, Y[4], MW, H_BOX, ["⑤ 本次返回里有工具调用请求吗？"], style=((240, 240, 248), (78, 88, 138)))
arrow([(MX + MW / 2, Y[4] + H_BOX), (MX + MW / 2, Y[5])], "有")

box(MX, Y[5], MW, H_BOX, ["⑥ 白名单 + 参数校验（程序）", "工具名在白名单？类型/范围/路径合规？"],
    style=CHECK, tag="参数校验")
arrow([(MX + MW / 2, Y[5] + H_BOX), (MX + MW / 2, Y[6])], "通过")

box(MX, Y[6], MW, H_BOX, ["⑦ 需要人工确认吗？（写操作）", "同意 / 拒绝 / 等待超时"],
    style=CONFIRM, tag="人工确认")
arrow([(MX + MW / 2, Y[6] + H_BOX), (MX + MW / 2, Y[7])], "只读或已同意")

box(MX, Y[7], MW, H_BOX, ["⑧ 执行工具（带超时）→ 结构化结果 / 错误"])
arrow([(MX + MW / 2, Y[7] + H_BOX), (MX + MW / 2, Y[8])])

box(MX, Y[8], MW, H_BOX, ["⑨ 结果以 role=tool 回传上下文", "（不是只打印：模型下一轮能看到）"])
arrow([(MX + 30, Y[8] + H_BOX), (MX + 30, Y[8] + H_BOX + 46), (MX - 40, Y[8] + H_BOX + 46),
       (MX - 40, Y[3] + H_BOX / 2), (MX, Y[3] + H_BOX / 2)], dashed=True)
d.text((MX - 30, Y[8] + H_BOX + 54), "回到 ④：工具结果作为新上下文，继续下一轮",
       font=f_note, fill=MUTED)

# ---------- 右侧：最终回答 → 程序校验 → 结束 ----------
arrow([(MX + MW, Y[4] + H_BOX / 2), (RX, Y[4] + H_BOX / 2)], "没有（最终回答）")
box(RX, Y[4], RW, H_BOX, ["⑩ 模型给出最终回答"], style=END)
arrow([(RX + RW / 2, Y[4] + H_BOX), (RX + RW / 2, Y[5])])
box(RX, Y[5], RW, H_BOX + 12, ["程序侧成功校验（程序）", "数字是否与工具结果一致？"], style=CHECK,
    tag="成功校验")
arrow([(RX + RW / 2, Y[5] + H_BOX + 12), (RX + RW / 2, Y[6])])
box(RX, Y[6], RW, H_BOX, ["结束：状态 + 步数 + 耗时", "并写入运行记录"], style=END)

# ---------- 左侧：各类“不走主路”的分支 ----------
box(LX, Y[2] - 6, LW, H_BOX, ["超限 → 结束任务", "状态 = max_steps / timeout"], style=END)
arrow([(MX, Y[2] + H_BOX / 2), (LX + LW, Y[2] + H_BOX / 2 - 6)], "超限")

box(LX, Y[5] - 6, LW, H_BOX + 6, ["校验失败 → 错误回传模型", "（模型可有限次修正参数）"], style=CONFIRM)
arrow([(MX, Y[5] + H_BOX / 2), (LX + LW, Y[5] + H_BOX / 2 - 6)])

box(LX, Y[6] - 6, LW, H_BOX + 6, ["拒绝 / 超时 → 不执行", "把“未确认”回传给模型"], style=CONFIRM)
arrow([(MX, Y[6] + H_BOX / 2), (LX + LW, Y[6] + H_BOX / 2 - 6)], "拒绝")

box(LX, Y[4] - 6, LW, H_BOX + 6, ["连续工具错误 ≥ 上限", "→ 结束（状态 = tool_errors）"], style=END)
arrow([(RX, Y[5] - 30), (LX + LW + 10, Y[4] + H_BOX - 20)], None, dashed=True)
d.text((LX, Y[4] + H_BOX + 14), "↑ 校验不通过时也可能直接结束", font=f_note, fill=MUTED)

# ---------- 图例 ----------
ly = 872
d.rounded_rectangle([MX - 60, ly, MX + MW + 60, ly + 128], radius=10, fill=(255, 255, 255),
                    outline=(202, 208, 218), width=1)
d.text((MX - 40, ly + 10), "图例", font=font(15, True), fill=INK)
legend = [(MAIN, "模型与程序协作的步骤"),
          (CHECK, "由程序执行的检查（参数 / 停止 / 成功校验）"),
          (CONFIRM, "人工确认与失败回传（不执行或修正）"),
          (END, "结束状态与运行记录")]
for i, (style, label) in enumerate(legend):
    x = MX - 40 + (i % 2) * 300
    y = ly + 40 + (i // 2) * 38
    d.rounded_rectangle([x, y, x + 24, y + 20], radius=5, fill=style[0], outline=style[1], width=2)
    d.text((x + 32, y + 1), label, font=f_note, fill=INK)
d.text((MX - 40, ly + 112), "关键限制全部由程序执行，不写在提示词里。", font=f_note, fill=MUTED)

out_dir = os.path.join("image", "实验6-工具调用、Agent与Harness实现")
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, "图3-Agent循环图.png")
img.save(out, "PNG")
print("已生成：%s  (%dx%d, %.0f KB)" % (out, W, H, os.path.getsize(out) / 1024))
