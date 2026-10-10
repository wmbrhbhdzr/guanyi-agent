# -*- coding: utf-8 -*-
"""
实验3《软件架构与界面设计》报告插图生成脚本
================================================
用途：用 Pillow 直接绘制报告所需的全部设计图（不依赖 Graphviz / PlantUML 等外部渲染器），
      便于在仓库中复现与修改。输出目录：image/实验3-软件架构与界面设计/

用法：
    .venv\\Scripts\\python.exe scripts\\draw_exp3_figs.py 1 2 3 4 5 6 7 8 9 10 11 12
    .venv\\Scripts\\python.exe scripts\\draw_exp3_figs.py all

说明：
    - 画布采用逻辑坐标，内部以 SS 倍超采样绘制后再缩小，保证线条与文字平滑；
    - 中文使用系统字体 msyh.ttc / msyhbd.ttc（微软雅黑），Windows 自带，无需额外字体文件。
"""

import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

# 折行用的最小单元：ASCII 单词整体成块（避免把 CapturePort 拆成 Captur/ePort），其余逐字成块
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:\\-]+|.")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "image", "实验3-软件架构与界面设计")
SS = 2  # 超采样倍数

FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

# ---- 统一配色 ----
C_UI = ("#EAF1FB", "#2F4B7C")        # 界面层
C_APP = ("#E8F5E9", "#2E7D32")       # 应用层
C_CORE = ("#FFF8E1", "#B26A00")      # 领域层
C_ADP = ("#F3E5F5", "#6A1B9A")       # 适配层
C_EXT = ("#ECEFF1", "#546E7A")       # 外部系统
C_AI = ("#E3F2FD", "#1565C0")        # AI 能力
C_DATA = ("#E0F2F1", "#00695C")      # 数据
C_EXEC = ("#FBE9E7", "#BF360C")      # 执行
C_HUMAN = ("#FFF3E0", "#E65100")     # 人工确认
C_WARN = "#D32F2F"                   # 禁止/异常
INK = "#1B2A38"                      # 正文
GREY = "#607D8B"

_font_cache = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_BOLD if bold else FONT_REG, int(round(size * SS)))
    return _font_cache[key]


class Canvas:
    """逻辑坐标画布：所有坐标按最终图片像素填写，内部自动超采样。"""

    def __init__(self, w, h, bg="#FFFFFF"):
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * SS, h * SS), bg)
        self.d = ImageDraw.Draw(self.img)

    # ---------- 基础图元 ----------
    def px(self, v):
        return v * SS

    def wrap(self, text, w, fs, bold=False):
        """按宽度折行：ASCII 单词不拆分，中文逐字折行。"""
        f = font(fs, bold)
        maxpx = self.px(w)
        out = []
        for para in str(text).split("\n"):
            cur = ""
            for ck in _TOKEN_RE.findall(para):
                if cur == "" or self.d.textlength(cur + ck, font=f) <= maxpx:
                    cur += ck
                else:
                    out.append(cur.rstrip())
                    cur = ck
            out.append(cur)
        return out

    def text(self, x, y, s, fs=19, bold=False, color=INK, align="l", valign="t"):
        f = font(fs, bold)
        lines = str(s).split("\n")
        lh = fs * 1.45
        total = len(lines) * lh
        y0 = y if valign == "t" else (y - total / 2 if valign == "c" else y - total)
        for i, ln in enumerate(lines):
            tw = self.d.textlength(ln, font=f) / SS
            x0 = x if align == "l" else (x - tw / 2 if align == "c" else x - tw)
            self.d.text((self.px(x0), self.px(y0 + i * lh)), ln, font=f, fill=color)

    def rect(self, x, y, w, h, fill=None, outline=None, r=0, lw=2, dash=None):
        box = [self.px(x), self.px(y), self.px(x + w), self.px(y + h)]
        if dash:
            self.dline((x, y), (x + w, y), outline, lw, dash)
            self.dline((x + w, y), (x + w, y + h), outline, lw, dash)
            self.dline((x + w, y + h), (x, y + h), outline, lw, dash)
            self.dline((x, y + h), (x, y), outline, lw, dash)
            return
        if r:
            self.d.rounded_rectangle(box, radius=self.px(r), fill=fill, outline=outline, width=int(lw * SS))
        else:
            self.d.rectangle(box, fill=fill, outline=outline, width=int(lw * SS) if outline else 0)

    def box(self, x, y, w, h, text="", fill="#FFFFFF", outline="#2F4B7C", r=10, fs=19,
            bold=False, lw=2, color=INK, pad=12, align="c", valign="c"):
        self.rect(x, y, w, h, fill=fill, outline=outline, r=r, lw=lw)
        if not text:
            return
        lines = self.wrap(text, w - 2 * pad, fs, bold)
        lh = fs * 1.5
        total = len(lines) * lh
        y0 = y + (h - total) / 2 if valign == "c" else y + pad
        for i, ln in enumerate(lines):
            f = font(fs, bold)
            if align == "c":
                tw = self.d.textlength(ln, font=f) / SS
                self.d.text((self.px(x + (w - tw) / 2), self.px(y0 + i * lh)), ln, font=f, fill=color)
            else:
                self.d.text((self.px(x + pad), self.px(y0 + i * lh)), ln, font=f, fill=color)

    def bullets(self, x, y, w, items, fs=18, lh=None, color=INK, bullet="· ", bold=False, gap=None):
        lh = lh or fs * 1.62
        gap = gap if gap is not None else fs * 0.55
        cy = y
        for it in items:
            lines = self.wrap(bullet + it, w, fs, bold)
            for i, ln in enumerate(lines):
                f = font(fs, bold)
                self.d.text((self.px(x + (0 if i == 0 else fs * 1.05)), self.px(cy)), ln, font=f, fill=color)
                cy += lh
            cy += gap
        return cy

    def dline(self, p1, p2, color=GREY, lw=2, dash=9, gap=7):
        x1, y1, x2, y2 = self.px(p1[0]), self.px(p1[1]), self.px(p2[0]), self.px(p2[1])
        total = math.hypot(x2 - x1, y2 - y1)
        if total == 0:
            return
        ux, uy = (x2 - x1) / total, (y2 - y1) / total
        pos = 0.0
        while pos < total:
            e = min(pos + dash * SS, total)
            self.d.line([x1 + ux * pos, y1 + uy * pos, x1 + ux * e, y1 + uy * e],
                        fill=color, width=max(1, int(lw * SS)))
            pos = e + gap * SS

    def line(self, p1, p2, color=GREY, lw=2):
        self.d.line([self.px(p1[0]), self.px(p1[1]), self.px(p2[0]), self.px(p2[1])],
                    fill=color, width=max(1, int(lw * SS)))

    def arrow(self, p1, p2, color="#2F4B7C", lw=2, dashed=False, head=True, hl=12, hw=6, dash=9, gap=7):
        x1, y1 = self.px(p1[0]), self.px(p1[1])
        x2, y2 = self.px(p2[0]), self.px(p2[1])
        ang = math.atan2(y2 - y1, x2 - x1)
        if head:
            hx = x2 - hl * SS * math.cos(ang)
            hy = y2 - hl * SS * math.sin(ang)
        else:
            hx, hy = x2, y2
        if dashed:
            self.dline(p1, (hx / SS, hy / SS), color, lw, dash, gap)
        else:
            self.d.line([x1, y1, hx, hy], fill=color, width=max(1, int(lw * SS)))
        if head:
            a = (x2 - hl * SS * math.cos(ang) - hw * SS * math.sin(ang),
                 y2 - hl * SS * math.sin(ang) + hw * SS * math.cos(ang))
            b = (x2 - hl * SS * math.cos(ang) + hw * SS * math.sin(ang),
                 y2 - hl * SS * math.sin(ang) - hw * SS * math.cos(ang))
            self.d.polygon([(x2, y2), a, b], fill=color)

    def elbow(self, pts, color="#2F4B7C", lw=2, dashed=False, head=True):
        for i in range(len(pts) - 1):
            last = (i == len(pts) - 2)
            if last:
                self.arrow(pts[i], pts[i + 1], color, lw, dashed, head)
            elif dashed:
                self.dline(pts[i], pts[i + 1], color, lw)
            else:
                self.line(pts[i], pts[i + 1], color, lw)

    def cross(self, x, y, s=9, color=C_WARN, lw=3):
        self.line((x - s, y - s), (x + s, y + s), color, lw)
        self.line((x - s, y + s), (x + s, y - s), color, lw)

    def circled(self, x, y, n, fill="#2F4B7C", r=14, fs=17, color="#FFFFFF"):
        """带编号的实心圆点，用于在箭头上做编号、避免长标签压线。"""
        self.d.ellipse([self.px(x - r), self.px(y - r), self.px(x + r), self.px(y + r)], fill=fill)
        self.text(x, y, str(n), fs=fs, bold=True, color=color, align="c", valign="c")

    def text_bg(self, x, y, s, fs=17, bold=False, color=INK, bg="#FFFFFF", align="l", pad=6):
        """带白色底衬的文字，防止被连线穿过。"""
        f = font(fs, bold)
        tw = self.d.textlength(s, font=f) / SS
        x0 = x if align == "l" else x - tw / 2
        self.rect(x0 - pad, y - 4, tw + 2 * pad, fs * 1.4 + 8, fill=bg, outline=None)
        self.text(x0, y, s, fs=fs, bold=bold, color=color)

    def para(self, x, y, w, s, fs=17, lh=None, color=INK, bold=False):
        """自动折行的整段文字，返回占用高度。"""
        lh = lh or fs * 1.55
        lines = self.wrap(s, w, fs, bold)
        for i, ln in enumerate(lines):
            self.text(x, y + i * lh, ln, fs=fs, bold=bold, color=color)
        return len(lines) * lh

    def save(self, name):
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, name)
        self.img.resize((self.w, self.h), Image.LANCZOS).save(path)
        print("saved %-56s %dx%d" % (name, self.w, self.h))
        return path


# =====================================================================
# 图 1　AI 与普通程序的职责边界图（对应 2.1）
# =====================================================================
def fig01():
    c = Canvas(1280, 800)
    cols = [
        (40, "交给 LLM（视觉语言模型）", C_AI,
         ["理解游戏画面：手牌、能量、敌人意图、自身状态组成的当前局面",
          "生成候选动作与一句可读依据",
          "判断“画面不可辨”并主动弃权（输出无法识别）",
          "把本局决策点串成复盘叙述"]),
        (450, "必须由规则程序完成", C_APP,
         ["截屏与窗口区域定位、画面有效性判定",
          "动作合法性校验（规则护栏，冲突时以规则为准）",
          "重试与失败恢复（同一动作最多 2 次）",
          "逐决策点记录、统计指标、档位与隐私控制"]),
        (860, "必须由人确认", C_HUMAN,
         ["首次使用／更换游戏时确认截图区域",
          "同一动作连续 2 次未生效时",
          "模型判断与规则校验冲突时",
          "切入“练习模式自动执行”之前"]),
    ]
    for x, title, (fill, edge), items in cols:
        c.rect(x, 40, 380, 56, fill=fill, outline=edge, r=10, lw=2)
        c.text(x + 190, 68, title, fs=20, bold=True, color=edge, align="c", valign="c")
        c.rect(x, 96, 380, 290, fill="#FFFFFF", outline=edge, r=10, lw=1.6)
        c.bullets(x + 16, 116, 348, items, fs=17, lh=26, gap=4)

    # 底部：核心流程流水线
    c.text(40, 418, "核心流程中各环节由谁负责：", fs=19, bold=True)
    names = ["屏幕像素", "LLM 理解\n与建议", "规则护栏\n校验", "玩家确认\n或执行", "逐决策点\n记录", "复盘报告"]
    xs = [40, 244, 448, 652, 856, 1060]
    for x, n in zip(xs, names):
        c.box(x, 450, 180, 74, n, fill="#FFFFFF", outline="#2F4B7C", r=8, fs=18)
    for i in range(5):
        c.arrow((xs[i] + 180, 487), (xs[i + 1], 487))
    c.text(40, 534, "实线：数据与调用方向（正常路径）", fs=16, color=GREY)

    # 禁止路径：模型绕过护栏直接触发执行
    c.elbow([(538, 524), (538, 556), (742, 556), (742, 524)], color=C_WARN, lw=2.2, dashed=True)
    c.cross(640, 556, s=10)
    c.text(430, 566, "禁止：模型输出不得绕过护栏直接触发执行", fs=17, bold=True, color=C_WARN)

    # 人工确认回环
    c.elbow([(730, 524), (730, 600), (1048, 600), (1048, 388)], color="#E65100", lw=2, dashed=True)
    c.text(766, 608, "异常／低置信／冲突 → 暂停并请求人工确认", fs=17, color="#E65100", bold=True)

    c.rect(40, 650, 1200, 140, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.4)
    c.text(58, 666, "边界小结", fs=18, bold=True)
    c.para(58, 700, 1160,
           "AI 只负责“看不懂就说不懂”的语义判断；合法性、重试次数、记录与统计一律由规则程序完成——"
           "规则护栏是 AI 的必要配套，而不是替代。判断权归模型，放行权归规则，最终决定权归玩家。",
           fs=17, lh=28)
    return c.save("图1-AI与程序职责边界.png")


# =====================================================================
# 图 2　软件与外部环境关系图（对应 2.3）
# =====================================================================
def fig02():
    c = Canvas(1300, 1040)

    # 本软件边界
    c.rect(430, 360, 440, 200, outline="#2F4B7C", lw=2, dash=9)
    c.text_bg(436, 330, "本软件边界（单个 Python 进程）", fs=17, bold=True, color="#2F4B7C")
    c.box(460, 390, 380, 140, "观弈（GuanYi）\n界面 · 编排 · 决策 · 护栏\n记录 · 报告 · 执行器 · 评测",
          fill=C_UI[0], outline=C_UI[1], r=14, fs=20, bold=True)

    # 四个外部对象
    c.box(540, 60, 280, 82, "玩家（主用户）\n切换档位 · 确认区域 · 阅读复盘",
          fill=C_HUMAN[0], outline=C_HUMAN[1], r=12, fs=17)
    c.box(60, 400, 290, 110, "游戏进程《杀戮尖塔》\n窗口化运行 · 本地单机", fill=C_EXT[0], outline=C_EXT[1], r=12, fs=18)
    c.box(950, 110, 300, 110, "云端 VLM 服务\nHTTPS · 按次计费 · 可替换为本地模型",
          fill=C_AI[0], outline=C_AI[1], r=12, fs=17)
    c.box(950, 650, 300, 120, "本地文件系统 runs/\n截图 · decisions.jsonl\nreport.md · memory.jsonl",
          fill=C_DATA[0], outline=C_DATA[1], r=12, fs=16)
    c.box(60, 650, 290, 120, "游戏真值通道\n（CommunicationMod）\n仅评测启用 · 默认关闭",
          fill="#FFEBEE", outline=C_WARN, r=12, fs=17)

    # 带编号的箭头
    c.arrow((600, 142), (600, 388))
    c.circled(600, 262, 1)
    c.arrow((700, 388), (700, 142))
    c.circled(700, 300, 2)
    c.arrow((350, 424), (458, 424))
    c.circled(404, 424, 3)
    c.arrow((458, 470), (352, 470), color="#546E7A", dashed=True)
    c.circled(404, 470, 4, fill="#546E7A")
    c.arrow((840, 400), (1000, 222), color=C_AI[1])
    c.circled(920, 311, 5, fill=C_AI[1])
    c.arrow((1040, 224), (844, 468), color=C_AI[1])
    c.circled(942, 346, 6, fill=C_AI[1])
    c.elbow([(840, 492), (890, 492), (890, 690), (948, 690)], color=C_DATA[1])
    c.circled(890, 590, 7, fill=C_DATA[1])
    c.elbow([(950, 722), (925, 722), (925, 570), (810, 570), (810, 532)], color=C_DATA[1])
    c.circled(925, 664, 8, fill=C_DATA[1])
    c.elbow([(350, 690), (400, 690), (400, 600), (505, 600), (505, 532)], color=C_WARN, dashed=True)
    c.circled(400, 646, 9, fill=C_WARN)
    c.text(60, 784, "红线：游戏真值不进入模型上下文，不得参与决策", fs=17, bold=True, color=C_WARN)

    # 编号说明
    c.rect(60, 812, 1180, 200, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.4)
    c.text(80, 826, "图中编号说明", fs=18, bold=True)
    left = ["① 玩家操作与档位切换 → 观弈；② 观弈输出建议卡与复盘报告 → 玩家",
            "③ 游戏窗口画面（仅窗口区域）→ 观弈；④ 键鼠输入（可选，默认关闭）→ 游戏",
            "⑤ 截图 + 通用动作 schema → 云端模型服务；⑥ 结构化建议或错误 → 观弈"]
    right = ["⑦ 运行记录写入本地 runs/（截图、JSONL、报告）",
             "⑧ 读取历史记录与既往报告",
             "⑨ 游戏内部状态 → 观弈：仅合法性校验与批量评测（默认关闭）"]
    for i, s in enumerate(left):
        c.text(80, 858 + i * 28, s, fs=15)
    for i, s in enumerate(right):
        c.text(690, 858 + i * 28, s, fs=15)
    c.text(80, 950, "外部依赖共 4 项：游戏进程（被采集、可被注入）、云端 VLM 服务（唯一按次计费的依赖）、本地文件系统（数据留存）、游戏真值通道（仅评测）。", fs=15, color=GREY)
    c.text(80, 978, "运行环境：Windows 11 + Python 3.13；断网时可切换为规则脚本决策（降级模式），软件仍可完整运行。", fs=15, color=GREY)
    return c.save("图2-软件与外部环境关系图.png")


# =====================================================================
# 图 3　总体架构图（分层 + 调用方向）
# =====================================================================
def fig03():
    c = Canvas(1400, 1010)
    X, W = 100, 980
    bands = [
        (40, "界面层\nui", C_UI, ["首页／入口", "设置页\n（区域与档位）", "核心任务页\n（建议卡）", "复盘报告页", "评测页\n（开发者）"]),
        (205, "应用层\napp", C_APP, ["用例编排：采集 →\n决策 → 护栏 → 记录 → 报告", "档位与配置管理", "生命周期与\n异常处理"]),
        (370, "领域层\ncore", C_CORE, ["领域数据模型", "提示强度策略", "请求组装与\n响应解析", "规则护栏", "结构化记忆", "端口协议\n（4 个 Port）"]),
        (535, "适配层\ninfra", C_ADP, ["mss 截屏\n（限窗口区域）", "模型客户端\n超时·重试·计费", "执行器三实现\nDryRun／SendInput\n／GameApi", "记录与报告\nJSONL·Markdown", "游戏真值适配器\n（仅评测，默认关闭）"]),
    ]
    for y, name, (fill, edge), items in bands:
        c.rect(X, y, W, 135, fill=fill, outline=edge, r=12, lw=2)
        c.text(X + 16, y + 68, name, fs=20, bold=True, color=edge, align="l", valign="c")
        inner_x = X + 130
        inner_w = (W - 150) / len(items)
        for i, it in enumerate(items):
            bx = inner_x + i * inner_w
            c.box(bx + 4, y + 18, inner_w - 12, 100, it, fill="#FFFFFF", outline=edge, r=8, fs=14, lw=1.4, pad=6)

    # 外部依赖行
    c.text(100, 688, "外部系统（不属于本软件）", fs=18, bold=True, color=C_EXT[1])
    ext = ["游戏窗口", "云端 VLM 服务", "本地文件系统 runs/", "游戏真值通道（评测）"]
    for i, n in enumerate(ext):
        c.box(100 + i * 250, 716, 230, 62, n, fill=C_EXT[0], outline=C_EXT[1], r=8, fs=16)

    # 调用方向
    c.arrow((40, 60), (40, 660), color="#2F4B7C", lw=2.4)
    c.text(8, 330, "调用／\n依赖方向", fs=14, bold=True, color="#2F4B7C")
    for y in (175, 340, 505):
        c.arrow((750, y), (750, y + 28), color="#2F4B7C", lw=2)
    c.dline((300, 670), (300, 716), "#546E7A", 2)
    c.dline((900, 670), (900, 716), "#546E7A", 2)

    # 右侧注解
    c.rect(1100, 370, 270, 170, fill="#FFF8E1", outline=C_CORE[1], r=10, lw=2)
    c.text(1116, 384, "依赖倒置", fs=18, bold=True, color=C_CORE[1])
    c.para(1116, 414, 238,
           "领域层只依赖自定的端口协议，不 import 任何适配器。\n四个端口：CapturePort · ModelPort · ExecutorPort · StoragePort。",
           fs=14, lh=20)

    c.rect(1100, 555, 270, 170, fill="#FFEBEE", outline=C_WARN, r=10, lw=2)
    c.text(1116, 569, "真值隔离", fs=18, bold=True, color=C_WARN)
    c.para(1116, 599, 238,
           "游戏真值只允许被评测模块与护栏读取；构造 Prompt 时显式丢弃真值字段，模型只看到像素与动作 schema。",
           fs=14, lh=20)

    c.rect(60, 800, 1280, 180, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.4)
    c.text(78, 814, "架构风格与数据流说明", fs=18, bold=True)
    c.bullets(78, 848, 1240, [
        "采用“分层 + 端口适配器”风格：上层只调用下层接口，界面层不直接访问适配层，避免界面与实现耦合。",
        "主数据流（一次决策）：界面层下发“开始／继续”→ 应用层编排 → 适配层截屏 → AI 能力出建议 → 领域层护栏校验 → 适配层记录 → 复盘报告回界面层展示。",
        "评测模块 eval 不经过界面层，直接调用应用层编排，便于无人值守批量运行（对应验收条件 A2）。",
    ], fs=15, lh=25, gap=2)
    return c.save("图3-总体架构图.png")


# =====================================================================
# 图 4　模块结构图（包图 + 依赖规则）
# =====================================================================
def fig04():
    c = Canvas(1280, 900)
    c.box(440, 40, 400, 76, "ui　界面层（Tkinter／ttk）", fill=C_UI[0], outline=C_UI[1], r=10, fs=19, bold=True)
    c.arrow((640, 116), (640, 156), color=C_UI[1], lw=2)

    c.box(320, 156, 640, 84, "app　应用层：用例编排 · 档位与配置 · 生命周期与异常处理",
          fill=C_APP[0], outline=C_APP[1], r=10, fs=19, bold=True)

    mods = [
        (60, "ai　AI 能力", C_AI, "Prompt 组装 · 模型客户端\n输出解析与校验 · 计费统计"),
        (350, "data　数据", C_DATA, "JSONL 记录 · 截图归档\n复盘报告生成 · 记忆库"),
        (640, "exec　执行器", C_EXEC, "Executor 端口\nDryRun／SendInput／GameApi"),
        (930, "eval　评测", ("#EDE7F6", "#4527A0"), "固定局面集批量运行\n指标计算与基线对比"),
    ]
    for x, name, (fill, edge), sub in mods:
        c.box(x, 300, 260, 116, name + "\n" + sub, fill=fill, outline=edge, r=10, fs=16, bold=True, pad=10)
    for x in (190, 480, 770, 1060):
        c.elbow([(640, 240), (640, 272), (x, 272), (x, 298)], color=C_APP[1], lw=1.8)

    c.box(180, 520, 920, 96, "core　领域层：领域数据模型 · 提示强度策略 · 请求／响应解析 · 规则护栏 · 结构化记忆 · 端口协议",
          fill=C_CORE[0], outline=C_CORE[1], r=10, fs=17, bold=True)
    for x in (190, 480, 770, 1060):
        c.elbow([(x, 416), (x, 470), (640, 470), (640, 518)], color=C_CORE[1], lw=1.8)

    c.rect(60, 650, 1160, 230, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.4)
    c.text(78, 664, "依赖规则（允许与禁止）", fs=18, bold=True)
    c.bullets(78, 698, 560, [
        "允许：ui → app；app → ai／data／exec／eval；适配模块 → core。",
        "禁止：core →（ai／data／exec／eval／ui）——不得依赖任何具体实现。",
        "禁止：ui →（ai／data／exec）直接调用，界面层只能经应用层。",
    ], fs=15, lh=25, gap=2)
    c.bullets(670, 698, 540, [
        "eval 经 app 调用编排，另可直接使用 data 与 exec 做批量评测。",
        "禁止：决策链路中出现游戏真值字段——真值只允许由 eval 与护栏读取。",
        "依赖方向单一：箭头一律指向被依赖方，不存在双向依赖。",
    ], fs=15, lh=25, gap=2)
    c.text(78, 856, "说明：图中 7 个包与图 3 的四层一一对应——ui 属界面层，app 属应用层，core 属领域层，ai／data／exec／eval 属适配层。",
           fs=15, color=GREY)
    return c.save("图4-模块结构图.png")


# =====================================================================
# 图 5　核心数据模型（类图／ER 风格）
# =====================================================================
def entity(c, x, y, w, h, title, fields, edge, fs=13):
    c.rect(x, y, w, h, fill="#FFFFFF", outline=edge, r=10, lw=1.8)
    c.text(x + w / 2, y + 9, title, fs=16, bold=True, color=edge, align="c")
    c.line((x + 10, y + 36), (x + w - 10, y + 36), edge, 1.4)
    c.bullets(x + 12, y + 46, w - 24, fields, fs=fs, lh=fs * 1.45, gap=1, bullet="")
    return y + h


def fig05():
    c = Canvas(1300, 940)
    BLUE, GREEN, PURPLE, ORANGE, TEAL = "#1F4E79", "#2E7D32", "#4527A0", "#B26A00", "#00695C"

    entity(c, 60, 60, 280, 150, "EvalResult　评测结果", [
        "eval_id (PK)｜seed_set｜baseline",
        "n_runs｜win_rate（胜率）",
        "avg_hp_loss｜variance（方差）",
        "created_at｜report_path",
    ], PURPLE)

    entity(c, 420, 60, 280, 170, "Run　一局运行", [
        "run_id (PK)｜game_title｜seed",
        "started_at｜ended_at｜status",
        "config_snapshot（档位／区域／模型版本）",
        "outcome（胜／负）｜hp_curve[]",
    ], BLUE)

    entity(c, 780, 60, 300, 150, "Report　复盘报告", [
        "report_id (PK)｜run_id (FK)",
        "generated_at｜path（report.md）",
        "key_points[]（关键决策点）",
        "summary（一段结论）",
    ], GREEN)

    entity(c, 420, 330, 320, 270, "DecisionPoint　决策点（核心实体）", [
        "dp_id (PK)｜run_id (FK)｜turn｜seq",
        "shot_id (FK)｜state_summary",
        "legal_actions[]（规则给出的合法集）",
        "suggestion{action, reason}｜confidence",
        "player_action｜is_consistent（建议与实际是否一致）",
        "model_meta{model, latency_ms, tokens_in/out, cost}",
        "result{hp_delta, enemy_hp_delta, outcome}",
    ], BLUE)

    entity(c, 60, 640, 280, 180, "Screenshot　截图", [
        "shot_id (PK)｜dp_id (FK)",
        "path｜width × height｜sha256",
        "captured_at｜region（窗口区域）",
        "is_valid（非黑屏／尺寸正常）",
    ], TEAL)

    entity(c, 420, 640, 320, 140, "Action　动作（值对象）", [
        "action_type（play_card／end_turn）",
        "card_name｜target｜energy_cost",
        "source（模型建议／玩家操作）",
    ], ORANGE)

    entity(c, 800, 620, 280, 190, "MemoryItem　记忆条目", [
        "mem_id (PK)｜state_signature",
        "action｜outcome｜lesson",
        "source_run_id (FK)｜hit_count",
        "created_at",
    ], ORANGE)

    def multi(x, y, s):
        c.text_bg(x, y, s, fs=13, color="#37474F", align="c")

    # EvalResult —— Run（一次评测包含多局）
    c.arrow((340, 135), (418, 135))
    multi(352, 108, "0..*")
    multi(400, 108, "1")
    # Run —— Report（一局一份报告）
    c.arrow((700, 135), (778, 135), color=GREEN)
    multi(716, 108, "1")
    multi(762, 108, "0..1")
    # Run —— DecisionPoint（一局多个决策点）
    c.arrow((560, 230), (560, 328), color=BLUE)
    multi(536, 258, "1")
    multi(536, 296, "1..*")
    # DecisionPoint —— Screenshot（一个决策点一张图）
    c.elbow([(420, 470), (300, 470), (300, 638)], color=TEAL)
    multi(316, 520, "1")
    multi(316, 596, "1")
    # DecisionPoint —— Action
    c.arrow((580, 600), (580, 638), color=ORANGE)
    multi(556, 610, "1")
    multi(556, 626, "1..*")
    # DecisionPoint —— MemoryItem（引用若干历史记忆）
    c.elbow([(740, 430), (770, 430), (770, 700), (798, 700)], color=ORANGE, dashed=True)
    multi(752, 500, "0..*")
    multi(752, 660, "0..1")

    c.rect(60, 840, 1180, 90, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.4)
    c.text(78, 852, "数据保存与敏感数据", fs=17, bold=True)
    c.para(78, 878, 1140,
           "全部实体落盘在 runs/<run_id>/ 下（screenshots/*.png、decisions.jsonl、report.md、memory.jsonl）；评测结果写入 runs/eval/<eval_id>.json。"
           "敏感项：截图只覆盖游戏窗口区域（对应 Q12 的隐私要求）；API 密钥只从环境变量读取，不进入任何数据实体。",
           fs=14, lh=22)
    return c.save("图5-核心数据模型.png")


# =====================================================================
# 图 6　核心流程顺序图（一次决策 + 异常路径）
# =====================================================================
def fig06():
    c = Canvas(1420, 960)
    lanes = [90, 268, 446, 624, 802, 980, 1158, 1336]
    heads = ["玩家", "界面层\nui", "应用层\napp", "截屏适配器\ncapture", "AI 能力\nVLM",
             "领域层\n护栏 core", "执行器\nexec（DryRun）", "数据层\ndata"]
    edges = ["#E65100", "#2F4B7C", "#2E7D32", "#6A1B9A", "#1565C0", "#B26A00", "#BF360C", "#00695C"]
    for x, h, e in zip(lanes, heads, edges):
        c.box(x - 82, 40, 164, 56, h, fill="#FFFFFF", outline=e, r=8, fs=14, bold=True, lw=1.8)
        c.dline((x, 100), (x, 830), "#B0BEC5", 1.4)
    c.rect(20, 20, 1380, 830, outline="#CFD8DC", r=12, lw=1.4)

    def msg(i, j, y, text, color="#2F4B7C", dashed=False, side="above"):
        x1, x2 = lanes[i], lanes[j]
        c.arrow((x1, y), (x2, y), color=color, lw=1.8, dashed=dashed, hl=11, hw=5)
        ty = y - 21 if side == "above" else y + 6
        c.text(min(x1, x2) + 6, ty, text, fs=13, color=color)

    def self_msg(i, y, text, color="#2F4B7C"):
        x = lanes[i]
        c.elbow([(x, y), (x + 34, y), (x + 34, y + 24), (x, y + 24)], color=color, lw=1.6)
        c.text(x + 42, y - 4, text, fs=13, color=color)

    msg(1, 2, 140, "① 开始／继续对局（档位＝仅复盘）", "#2F4B7C")
    msg(2, 3, 184, "② 截取游戏窗口区域", "#6A1B9A")
    self_msg(3, 208, "③ 画面有效性判定：非黑屏、尺寸正常", "#6A1B9A")
    msg(3, 2, 262, "④ 截图 PNG（含 sha256）", "#6A1B9A")
    msg(2, 4, 306, "⑤ 决策请求：截图 + 通用动作 schema（不含任何游戏真值）", "#1565C0")
    self_msg(4, 330, "⑥ 解析为结构化 JSON；空返回则重试 1 次", "#1565C0")
    msg(4, 2, 386, "⑦ {动作, 依据, 置信度}", "#1565C0")
    msg(2, 5, 430, "⑧ 合法性校验（动作 ∈ legal_actions）", "#B26A00")
    msg(5, 2, 470, "⑨ allow / deny + 原因", "#B26A00")
    msg(2, 7, 512, "⑩ 记录决策点（JSONL + 截图归档）", "#00695C")
    msg(2, 6, 556, "⑪ 应用动作（默认 DryRun：不注入任何输入）", "#BF360C")
    msg(6, 2, 596, "⑫ ok / injection_failure", "#BF360C")
    msg(2, 1, 640, "⑬ 更新建议卡与状态条（时延、费用、是否记录）", "#2F4B7C")
    msg(2, 7, 688, "⑭ 战斗结束：生成逐回合复盘报告", "#00695C")
    msg(7, 1, 728, "⑮ 报告路径 → 界面展示复盘", "#00695C")

    # 异常路径
    msg(4, 2, 408, "低置信／无法识别 → 暂停并请求人工确认（记录 low_confidence）", C_WARN, dashed=True, side="below")
    msg(5, 2, 492, "冲突 → 以规则为准，记录 guardrail_trigger", C_WARN, dashed=True, side="below")
    msg(6, 2, 618, "连续 2 次未生效 → 停止执行，记录 injection_failure", C_WARN, dashed=True, side="below")

    c.rect(20, 862, 1380, 84, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.4)
    c.text(38, 874, "约定", fs=16, bold=True)
    c.para(38, 898, 1340,
           "蓝色为正常调用，红色虚线为异常路径：三条异常分支都必须先落盘再提示，且都不会自动继续（对应验收条件 A3／A4／A5）。"
           "橙色人工确认点出现时，界面以模态提示给出“重拍截图／跳过该决策点／结束本局”三个选项。",
           fs=14, lh=22)
    return c.save("图6-核心流程顺序图.png")


# =====================================================================
# 图 7　失败恢复状态图
# =====================================================================
def fig07():
    c = Canvas(1300, 940)
    def st(x, y, w, h, name, fill, edge, fs=16):
        c.rect(x, y, w, h, fill=fill, outline=edge, r=12, lw=1.8)
        c.text(x + w / 2, y + h / 2, name, fs=fs, bold=True, color=edge, align="c", valign="c")

    GREY = "#546E7A"
    st(60, 80, 200, 90, "空闲 Idle", C_UI[0], C_UI[1])
    st(300, 80, 200, 90, "采集中 Capturing", C_ADP[0], C_ADP[1])
    st(540, 80, 200, 90, "决策中 Deciding", C_AI[0], C_AI[1])
    st(780, 80, 200, 90, "校验中 Guarding", C_CORE[0], C_CORE[1])
    st(1020, 80, 200, 90, "执行中 Applying", C_EXEC[0], C_EXEC[1])
    st(60, 250, 340, 100, "等待人工确认 WaitingHuman", C_HUMAN[0], C_HUMAN[1], fs=17)
    st(460, 250, 280, 100, "已暂停 Paused", "#ECEFF1", GREY, fs=17)
    st(760, 250, 240, 100, "已终止 Aborted", "#FFEBEE", C_WARN, fs=17)
    st(1040, 250, 180, 90, "记录中\nRecording", C_DATA[0], C_DATA[1], fs=15)
    st(1040, 430, 180, 90, "本局完成\nDone", C_APP[0], C_APP[1], fs=15)

    def lab(x, y, s, color=INK, fs=13):
        c.text_bg(x, y, s, fs=fs, color=color)

    # 正常路径
    c.arrow((260, 125), (298, 125)); lab(268, 96, "开始对局")
    c.arrow((500, 125), (538, 125)); lab(508, 96, "画面有效")
    c.arrow((740, 125), (778, 125)); lab(748, 96, "输出可解析")
    c.arrow((980, 125), (1018, 125)); lab(988, 96, "allow")
    c.arrow((1120, 170), (1120, 248)); lab(1132, 196, "执行后画面已变化")
    c.arrow((1120, 340), (1120, 428)); lab(1132, 366, "战斗结束")
    # 循环：记录完成 → 下一个决策点
    c.elbow([(1040, 275), (1000, 275), (1000, 232), (350, 232), (350, 78)], color="#1565C0", lw=1.6, dashed=True)
    lab(430, 206, "已落盘 → 处理下一个决策点", "#1565C0")
    # 异常 → 等待人工确认
    c.elbow([(560, 170), (560, 196), (230, 196), (230, 248)], color=C_HUMAN[1], lw=1.6, dashed=True)
    lab(238, 172, "无法识别／空返回（重试 1 次后）", C_HUMAN[1])
    c.elbow([(800, 170), (800, 214), (300, 214), (300, 248)], color=C_HUMAN[1], lw=1.6, dashed=True)
    lab(610, 176, "冲突 → 以规则为准", C_HUMAN[1])
    # 人工处理 / 暂停 / 终止
    c.elbow([(1120, 80), (1120, 56), (680, 56), (680, 248)], color=GREY, lw=1.6, dashed=True)
    lab(700, 34, "任意状态：玩家暂停", GREY)
    c.elbow([(460, 300), (420, 300), (420, 172)], color="#1565C0", lw=1.6, dashed=True)
    lab(196, 232, "恢复运行", "#1565C0")
    c.elbow([(140, 250), (140, 172)], color="#1565C0", lw=1.6, dashed=True)
    lab(46, 196, "人工处理后返回", "#1565C0")
    c.elbow([(300, 350), (300, 480), (880, 480), (880, 352)], color=C_WARN, lw=1.6, dashed=True)
    lab(520, 456, "失败达上限／人工选择终止", C_WARN)
    c.elbow([(940, 350), (940, 520), (430, 520), (430, 172)], color=C_WARN, lw=1.6, dashed=True)
    lab(600, 496, "人工处理后继续", C_WARN)

    c.rect(60, 600, 1180, 310, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.4)
    c.text(78, 614, "状态说明与恢复策略", fs=17, bold=True)
    c.bullets(78, 648, 1140, [
        "实线＝正常流转；橙色虚线＝异常转入“等待人工确认”；灰色虚线＝玩家主动暂停；红色虚线＝终止与恢复；蓝色虚线＝循环与恢复。",
        "重试上限：模型超时或空返回重试 1 次；动作注入未生效重试不超过 2 次；达到上限后一律停止自动执行并提示，不出现无限重试（对应 A4）。",
        "校验冲突时以规则为准并记录 guardrail_trigger，界面提示玩家确认（对应 A5）；画面不可辨时不猜测，记录 low_confidence 并暂停（对应 A3）。",
        "等待人工确认状态下提供三个明确出口：重拍截图继续、跳过该决策点、结束本局；无人值守的批量评测模式下自动选择“跳过该局并记录”，不阻塞批次。",
    ], fs=15, lh=24, gap=4)
    return c.save("图7-失败恢复状态图.png")


# =====================================================================
# 图 9　界面原型：首页／入口页
# =====================================================================
def fig09():
    c = Canvas(1450, 880)
    INK2, EDGE, MUTE = "#37474F", "#90A4AE", "#78909C"

    def btn(x, y, w, h, label, primary=False, disabled=False, fs=14):
        if disabled:
            fill, edge, col = "#EEEEEE", "#BDBDBD", "#9E9E9E"
        elif primary:
            fill, edge, col = "#2F4B7C", "#2F4B7C", "#FFFFFF"
        else:
            fill, edge, col = "#FFFFFF", EDGE, INK2
        c.box(x, y, w, h, label, fill=fill, outline=edge, r=8, fs=fs, bold=primary, color=col, lw=1.6)

    def radio(x, y, label, on=False):
        r = 7
        if on:
            c.d.ellipse([c.px(x - r), c.px(y - r), c.px(x + r), c.px(y + r)], fill="#2F4B7C")
        else:
            c.d.ellipse([c.px(x - r), c.px(y - r), c.px(x + r), c.px(y + r)], outline=MUTE, width=int(1.6 * SS))
        c.text(x + 14, y - 9, label, fs=14, color=INK)

    def bar(x, y, w, h, ratio, color="#2F4B7C"):
        c.rect(x, y, w, h, fill="#CFD8DC", outline=None, r=h / 2)
        c.rect(x, y, max(8, w * ratio), h, fill=color, outline=None, r=h / 2)

    def block(x, y, w, h, n, title, fs=15):
        c.rect(x, y, w, h, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.5)
        c.circled(x + 18, y + 19, n, r=13, fs=15)
        c.text(x + 38, y + 11, title, fs=fs, bold=True, color=INK2)

    c.text(500, 58, "正常态", fs=15, bold=True, color=GREY, align="c")
    c.text(1195, 58, "异常状态", fs=15, bold=True, color=GREY, align="c")

    # ---------- 窗口外框 ----------
    WX, WY, WW, WH = 50, 80, 900, 620
    c.rect(WX + 2, WY + 2, WW - 4, 38, fill="#ECEFF1", outline=None)
    c.rect(WX, WY, WW, WH, fill=None, outline=EDGE, r=10, lw=2)
    c.line((WX + 2, WY + 40), (WX + WW - 2, WY + 40), EDGE, 1.4)
    c.text(WX + 18, WY + 12, "观弈 GuanYi", fs=15, bold=True, color=INK2)
    c.text(WX + WW - 18, WY + 13, "—    ▢    ✕", fs=13, color=MUTE, align="r")

    # 顶部状态条
    c.rect(80, 138, 840, 44, fill="#FFFFFF", outline="#CFD8DC", r=8, lw=1.4)
    c.d.ellipse([c.px(100), c.px(153), c.px(112), c.px(165)], fill="#2E7D32")
    c.text(122, 148, "模型服务：已连接 deepseek-flash", fs=13, color=INK2)
    c.text(500, 148, "密钥来源：环境变量", fs=13, color=INK2)
    c.text(700, 148, "当前档位：仅复盘", fs=13, bold=True, color="#2F4B7C")

    # ① 当前游戏与窗口
    block(80, 200, 840, 122, 1, "当前游戏与窗口")
    c.text(96, 252, "当前游戏", fs=13, color=MUTE)
    c.box(176, 242, 236, 36, "《杀戮尖塔》（窗口化）", fill="#FFFFFF", outline=EDGE, r=6, fs=13, align="l", pad=10)
    c.text(400, 250, "▾", fs=15, color=MUTE)
    btn(432, 242, 150, 36, "选择截图区域")
    c.rect(620, 236, 280, 74, fill="#FFFFFF", outline=EDGE, dash=8, lw=1.5, r=8)
    c.text(760, 256, "窗口区域预览", fs=13, color=MUTE, align="c")
    c.text(760, 278, "（仅游戏窗口）", fs=12, color=MUTE, align="c")

    # ② 主操作
    block(80, 336, 840, 116, 2, "主操作")
    btn(96, 372, 240, 58, "开始对局", primary=True, fs=16)
    btn(352, 372, 240, 58, "仅复盘模式（悬浮条）", fs=14)
    btn(608, 372, 240, 58, "打开最近复盘", fs=14)

    # ③ 提示强度档位
    block(80, 466, 520, 116, 3, "提示强度档位")
    radio(104, 516, "仅复盘（默认）", on=True)
    radio(268, 516, "卡关时建议")
    radio(410, 516, "逐决策点建议")
    c.text(96, 546, "切档立即生效；默认档在游玩时不介入", fs=12, color=MUTE)

    # ④ 运行目录与版本
    block(620, 466, 300, 116, 4, "运行目录与版本")
    c.text(636, 506, "运行目录：runs/", fs=13, color=INK2)
    c.text(636, 528, "最近一局：run-0007（胜，9 月 28 日）", fs=13, color=INK2)
    c.text(636, 550, "版本 v0.1", fs=13, color=MUTE)

    # 窗口内底部提示条
    c.rect(80, 622, 840, 52, fill="#FFFFFF", outline="#CFD8DC", r=8, lw=1.4)
    c.text(96, 640, "提示：首次使用请先在设置页确认截图区域与提示强度档位（默认“仅复盘”）", fs=13, color=MUTE)
    btn(790, 632, 118, 32, "去设置 →", fs=13)

    # ---------- 右侧：三种状态 ----------
    c.circled(1006, 110, 5, r=13, fs=15)
    c.text(1026, 102, "三种状态的界面表现", fs=15, bold=True, color=INK2)

    c.rect(990, 140, 410, 146, fill="#F5F5F5", outline=MUTE, dash=9, lw=1.6, r=10)
    c.text(1006, 154, "加载中（请求中）", fs=15, bold=True, color=INK2)
    c.text(1006, 184, "正在检测游戏窗口…", fs=13, color=MUTE)
    bar(1006, 212, 236, 12, 0.55)
    c.text(1254, 208, "约 2—3 秒，可取消", fs=12, color=MUTE)

    c.rect(990, 306, 410, 176, fill="#FFFFFF", outline=MUTE, dash=9, lw=1.6, r=10)
    c.text(1006, 320, "空数据", fs=15, bold=True, color=INK2)
    c.text(1006, 350, "未检测到《杀戮尖塔》窗口", fs=13, color=INK2)
    c.text(1006, 372, "请先把游戏切到窗口化并启动", fs=13, color=MUTE)
    btn(1006, 420, 140, 36, "重新检测")

    c.rect(990, 502, 410, 196, fill="#FFEBEE", outline=C_WARN, dash=9, lw=1.6, r=10)
    c.text(1006, 516, "错误", fs=15, bold=True, color=C_WARN)
    c.text(1006, 546, "未从环境变量读取到 API 密钥", fs=13, color=INK2)
    c.text(1006, 568, "修复后按钮自动恢复可用", fs=13, color=MUTE)
    btn(1006, 616, 140, 38, "开始对局", disabled=True, fs=15)
    c.text(1160, 626, "该按钮当前置灰（输入限制）", fs=12, bold=True, color=C_WARN)

    # ---------- 图下注释 ----------
    c.rect(50, 748, 1340, 100, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.4)
    c.text(68, 762, "编号说明", fs=15, bold=True)
    c.para(68, 790, 1300,
           "① 当前游戏与窗口　② 主操作　③ 提示强度档位（默认“仅复盘”）　④ 运行目录与版本　⑤ 加载／空数据／错误三种状态的界面表现。"
           "注意：密钥未配置时“开始对局”置灰；截图区域只覆盖游戏窗口，不采集整屏；档位切换立即生效。",
           fs=14, lh=24)
    return c.save("图9-界面原型-首页.png")


# =====================================================================
# 界面原型通用构件（图 10—图 12 共用；图 9 用的是等价的内联写法）
# =====================================================================
U_EDGE, U_INK, U_MUTE = "#90A4AE", "#37474F", "#78909C"


def ui_btn(c, x, y, w, h, label, primary=False, disabled=False, fs=14):
    if disabled:
        fill, edge, col = "#EEEEEE", "#BDBDBD", "#9E9E9E"
    elif primary:
        fill, edge, col = "#2F4B7C", "#2F4B7C", "#FFFFFF"
    else:
        fill, edge, col = "#FFFFFF", U_EDGE, U_INK
    c.box(x, y, w, h, label, fill=fill, outline=edge, r=8, fs=fs, bold=primary, color=col, lw=1.6)


def ui_radio(c, x, y, label, on=False, fs=14):
    r = 7
    if on:
        c.d.ellipse([c.px(x - r), c.px(y - r), c.px(x + r), c.px(y + r)], fill="#2F4B7C")
    else:
        c.d.ellipse([c.px(x - r), c.px(y - r), c.px(x + r), c.px(y + r)], outline=U_MUTE, width=int(1.6 * SS))
    c.text(x + 14, y - 9, label, fs=fs, color=INK)


def ui_check(c, x, y, label, on=True, fs=13):
    c.rect(x - 8, y - 8, 16, 16, fill="#2F4B7C" if on else "#FFFFFF", outline=U_MUTE, r=3, lw=1.4)
    if on:
        ui_tick(c, x, y + 1, s=8, color="#FFFFFF", lw=2.2)
    c.text(x + 16, y - 9, label, fs=fs, color=INK)


def ui_tri(c, cx, cy, w=10, h=6, color=U_MUTE):
    """向下小三角（用画的，避免字体缺字）"""
    c.d.polygon([(c.px(cx - w / 2), c.px(cy - h / 2)), (c.px(cx + w / 2), c.px(cy - h / 2)),
                 (c.px(cx), c.px(cy + h / 2))], fill=color)


def ui_tick(c, cx, cy, s=9, color="#2E7D32", lw=2.4):
    """对勾（用画的）"""
    c.line((cx - s * 0.55, cy - s * 0.05), (cx - s * 0.12, cy + s * 0.42), color, lw)
    c.line((cx - s * 0.12, cy + s * 0.42), (cx + s * 0.58, cy - s * 0.45), color, lw)


def ui_crossmark(c, cx, cy, s=8, color=C_WARN, lw=2.4):
    """叉号（用画的）"""
    c.line((cx - s * 0.45, cy - s * 0.45), (cx + s * 0.45, cy + s * 0.45), color, lw)
    c.line((cx - s * 0.45, cy + s * 0.45), (cx + s * 0.45, cy - s * 0.45), color, lw)


def ui_bar(c, x, y, w, h, ratio, color="#2F4B7C"):
    c.rect(x, y, w, h, fill="#CFD8DC", outline=None, r=h / 2)
    c.rect(x, y, max(8, w * ratio), h, fill=color, outline=None, r=h / 2)


def ui_block(c, x, y, w, h, n, title, fs=15):
    c.rect(x, y, w, h, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.5)
    c.circled(x + 18, y + 19, n, r=13, fs=15)
    c.text(x + 38, y + 11, title, fs=fs, bold=True, color=U_INK)


def ui_window(c, x, y, w, h, title="观弈 GuanYi"):
    c.rect(x + 2, y + 2, w - 4, 38, fill="#ECEFF1", outline=None)
    c.rect(x, y, w, h, fill=None, outline=U_EDGE, r=10, lw=2)
    c.line((x + 2, y + 40), (x + w - 2, y + 40), U_EDGE, 1.4)
    c.text(x + 18, y + 12, title, fs=15, bold=True, color=U_INK)
    c.text(x + w - 18, y + 13, "—    ▢    ✕", fs=13, color=U_MUTE, align="r")


def ui_card(c, x, y, w, h, title, color=U_MUTE, fill="#FFFFFF", fs=15):
    c.rect(x, y, w, h, fill=fill, outline=color, dash=9, lw=1.6, r=10)
    c.text(x + 16, y + 14, title, fs=fs, bold=True, color=INK if color == U_MUTE else color)


def ui_dropdown(c, x, y, w, h, text, fs=13):
    c.box(x, y, w, h, text, fill="#FFFFFF", outline=U_EDGE, r=6, fs=fs, align="l", pad=10, color=U_INK)
    ui_tri(c, x + w - 16, y + h / 2, 10, 6)


def ui_input(c, x, y, w, h, text, fs=13, fill="#FFFFFF", color=None):
    c.box(x, y, w, h, text, fill=fill, outline=U_EDGE, r=6, fs=fs, align="l", pad=10, color=color or U_INK)


def ui_legend(c, x, y, w, text, h=100):
    c.rect(x, y, w, h, fill="#FAFAFA", outline="#CFD8DC", r=10, lw=1.4)
    c.text(x + 18, y + 14, "编号说明", fs=15, bold=True)
    c.para(x + 18, y + 42, w - 36, text, fs=14, lh=24)


def ui_top_labels(c, left_cx, right_cx, y=58):
    c.text(left_cx, y, "正常态", fs=15, bold=True, color=GREY, align="c")
    c.text(right_cx, y, "异常状态", fs=15, bold=True, color=GREY, align="c")


def ui_small(c, x, y, s, fs=12, color=None, bold=False):
    c.text(x, y, s, fs=fs, color=color or U_MUTE, bold=bold)


# =====================================================================
# 图 10　界面原型：设置页
# =====================================================================
def fig10():
    c = Canvas(1500, 900)
    ui_top_labels(c, 500, 1195)
    ui_window(c, 50, 80, 900, 620)

    # ① 截图区域
    ui_block(c, 80, 134, 840, 118, 1, "截图区域")
    ui_small(c, 96, 168, "选择窗口")
    ui_dropdown(c, 176, 160, 220, 36, "杀戮尖塔（窗口化）")
    ui_btn(c, 416, 160, 140, 36, "框选区域")
    c.rect(600, 146, 300, 96, fill="#FFFFFF", outline=U_EDGE, dash=8, lw=1.5, r=8)
    c.text(750, 166, "1280 × 720 @ (120, 80)", fs=13, color=U_INK, align="c")
    c.text(750, 198, "只截游戏窗口，不采集整屏", fs=12, bold=True, color=C_WARN, align="c")

    # ② 提示强度档位
    ui_block(c, 80, 264, 840, 104, 2, "提示强度档位")
    ui_radio(c, 104, 308, "仅复盘（默认）", on=True)
    ui_radio(c, 268, 308, "卡关时建议")
    ui_radio(c, 410, 308, "逐决策点建议")
    ui_small(c, 96, 336, "默认档在游玩时不介入，只记录与复盘")

    # ③ 模型服务
    ui_block(c, 80, 380, 840, 124, 3, "模型服务")
    ui_small(c, 96, 416, "服务商")
    ui_dropdown(c, 176, 410, 150, 34, "云端 API")
    ui_small(c, 350, 416, "接口地址")
    ui_input(c, 440, 410, 330, 34, "https://api.deepseek.com/chat/completions", fs=12)
    c.text(96, 466, "密钥：已从环境变量读取", fs=13, color=U_INK)
    c.text(286, 468, "●●●●●●", fs=13, color=U_MUTE)
    ui_btn(c, 620, 462, 110, 32, "测试连接", fs=13)

    # ④ 数据与隐私
    ui_block(c, 80, 516, 840, 120, 4, "数据与隐私")
    ui_input(c, 96, 540, 400, 34, "运行目录：runs/", fill="#F5F5F5")
    ui_btn(c, 508, 540, 110, 34, "打开目录", fs=13)
    ui_check(c, 110, 594, "保存截图（仅窗口区域）")
    ui_btn(c, 620, 584, 170, 34, "清理 30 天前的记录", fs=13)

    # ⑤ 底部命令
    c.rect(80, 648, 840, 44, fill="#FFFFFF", outline="#CFD8DC", r=10, lw=1.4)
    c.circled(102, 670, 5, r=13, fs=15)
    c.text(122, 662, "底部命令", fs=14, bold=True, color=U_INK)
    ui_small(c, 240, 664, "修改后点击“保存”生效")
    ui_btn(c, 600, 656, 92, 28, "保存", primary=True, fs=13)
    ui_btn(c, 700, 656, 100, 28, "恢复默认", fs=13)
    ui_btn(c, 808, 656, 96, 28, "返回", fs=13)

    # 右侧：输入限制与状态
    c.text(1006, 106, "输入限制与状态", fs=15, bold=True, color=U_INK)
    ui_card(c, 990, 140, 410, 180, "错误：输入限制", C_WARN, "#FFEBEE")
    c.text(1006, 174, "截图区域过小：当前 320×200，要求 ≥400×300", fs=13, color=U_INK)
    c.text(1006, 198, "请重新框选，至少覆盖整个游戏窗口", fs=13, color=U_MUTE)
    ui_btn(c, 1006, 266, 120, 36, "保存", disabled=True, fs=14)
    c.text(1140, 276, "该按钮当前置灰", fs=12, bold=True, color=C_WARN)

    ui_card(c, 990, 344, 410, 190, "操作反馈：保存成功", "#2E7D32", "#F1F8E9")
    c.text(1006, 378, "设置已写入 config_snapshot", fs=13, color=U_INK)
    c.text(1006, 402, "档位：仅复盘　区域：1280 × 720", fs=13, color=U_INK)
    ui_btn(c, 1006, 478, 150, 36, "立即开始对局", fs=14)

    ui_card(c, 990, 558, 410, 130, "加载中", U_MUTE)
    c.text(1006, 592, "正在测试模型连接…", fs=13, color=U_MUTE)
    ui_bar(c, 1006, 620, 236, 12, 0.6)
    ui_small(c, 1254, 616, "约 2 秒")

    ui_legend(c, 50, 748, 1400,
              "① 截图区域（限游戏窗口）　② 提示强度档位　③ 模型与密钥（掩码显示）　④ 数据与隐私　⑤ 底部命令；"
              "右侧为输入限制、操作反馈与加载状态。")
    return c.save("图10-界面原型-设置页.png")


# =====================================================================
# 图 11　界面原型：核心任务页（含悬浮条）
# =====================================================================
def fig11():
    c = Canvas(1500, 900)

    # 悬浮条（贴在游戏窗口顶端，画在窗口外上方）
    c.circled(40, 41, 5, r=13, fs=15)
    c.rect(60, 20, 560, 42, fill="#FFFFFF", outline=U_MUTE, dash=8, lw=1.6, r=8)
    c.text(76, 32, "观弈·仅复盘 ｜ 已记录 12 个决策点", fs=13, color=U_INK)
    ui_btn(c, 466, 28, 66, 26, "展开", fs=12)
    ui_btn(c, 540, 28, 68, 26, "暂停", fs=12)

    ui_top_labels(c, 540, 1290, 84)
    ui_window(c, 50, 100, 980, 620)

    # ① 局面区
    ui_block(c, 80, 152, 380, 400, 1, "局面区")
    c.rect(96, 200, 348, 236, fill="#FFFFFF", outline=U_EDGE, dash=8, lw=1.5, r=8)
    c.text(270, 310, "游戏窗口截图", fs=14, color=U_MUTE, align="c")
    c.text(270, 336, "（仅窗口区域）", fs=12, color=U_MUTE, align="c")
    for i, t in enumerate(["回合 3", "能量 3/3", "手牌 5 张", "敌人意图：攻击 11"]):
        c.text(96, 458 + i * 26, t, fs=13, color=U_INK)

    # ② 建议卡
    ui_block(c, 476, 152, 300, 400, 2, "建议卡")
    c.text(492, 188, "建议动作", fs=14, bold=True, color=U_MUTE)
    c.text(492, 220, "打出【打击】 → 颚虫", fs=18, bold=True, color="#2F4B7C")
    c.line((492, 264), (744, 264), "#CFD8DC", 1.2)
    c.para(492, 282, 268, "先用低费攻击压低敌方血量，保留能量给防御牌", fs=13, lh=22)
    ui_bar(c, 492, 358, 180, 12, 0.78)
    ui_small(c, 682, 354, "置信度 78%")
    c.text(492, 400, "为什么这样打", fs=13, color="#1565C0")
    ui_tri(c, 582, 406, 10, 6, "#1565C0")

    # ③ 操作区
    ui_block(c, 792, 152, 218, 400, 3, "操作区")
    ui_btn(c, 808, 200, 186, 44, "采用建议", primary=True, fs=15)
    ui_btn(c, 808, 256, 186, 44, "我自己打", fs=14)
    ui_btn(c, 808, 312, 186, 44, "跳过此决策点", fs=14)
    ui_btn(c, 808, 368, 186, 44, "暂停", fs=14)
    ui_small(c, 808, 438, "决策权在你")

    # ④ 状态栏
    c.rect(80, 568, 930, 60, fill="#FFFFFF", outline="#CFD8DC", r=10, lw=1.4)
    c.circled(102, 598, 4, r=13, fs=15)
    for i, t in enumerate(["本次决策 2.1 s", "累计费用 0.014 元", "已记录 12 个决策点", "模型 deepseek-flash"]):
        c.text(136 + i * 220, 590, t, fs=13, color=U_INK)

    # 窗口内提示
    c.rect(80, 650, 930, 52, fill="#FFFFFF", outline="#CFD8DC", r=8, lw=1.4)
    c.text(96, 668, "建议仅供参考，实际出牌由你决定；按 P 暂停记录", fs=13, color=U_MUTE)

    # 右侧：加载与人工确认
    c.text(1096, 106, "状态与异常", fs=15, bold=True, color=U_INK)
    ui_card(c, 1080, 140, 420, 180, "加载中（请求中）", U_MUTE)
    c.rect(1096, 180, 388, 50, fill="#ECEFF1", outline=None, r=6)
    c.text(1290, 196, "建议卡位置：正在读屏分析", fs=13, color=U_MUTE, align="c")
    ui_bar(c, 1096, 248, 260, 12, 0.45)
    ui_small(c, 1368, 244, "约 2—3 秒")
    ui_btn(c, 1096, 278, 90, 30, "取消", fs=13)

    ui_card(c, 1080, 344, 420, 220, "需要你的确认", "#E65100", "#FFF3E0")
    c.text(1096, 380, "这一手看不出关键局面，已暂停记录", fs=13, color=U_INK)
    c.text(1096, 404, "请选择下一步：", fs=13, color=U_MUTE)
    ui_btn(c, 1096, 490, 110, 36, "重拍截图", fs=13)
    ui_btn(c, 1216, 490, 140, 36, "跳过该决策点", fs=13)
    ui_btn(c, 1366, 490, 118, 36, "结束本局", fs=13)

    ui_legend(c, 50, 748, 1400,
              "① 局面区　② 建议卡（动作 + 一句依据 + 置信度）　③ 操作区　④ 状态栏（时延／费用／已记录）　"
              "⑤ 仅复盘档的悬浮条（贴在游戏窗口顶端，不遮挡游玩）；右侧为加载与人工确认状态。")
    return c.save("图11-界面原型-核心任务页.png")


# =====================================================================
# 图 12　界面原型：复盘报告页（结果页）
# =====================================================================
def fig12():
    c = Canvas(1500, 1000)
    ui_top_labels(c, 540, 1290, 76)
    ui_window(c, 50, 100, 980, 740)

    # ① 结果摘要
    ui_block(c, 80, 152, 930, 110, 1, "结果摘要")
    c.text(96, 200, "本局：胜利 · 第 3 层 · 剩余 HP 42/80", fs=16, bold=True, color="#2E7D32")
    c.rect(620, 166, 374, 84, fill="#FFFFFF", outline="#CFD8DC", r=8, lw=1.4)
    c.text(628, 172, "HP 曲线", fs=12, color=U_MUTE)
    pts = [(648, 236), (704, 212), (756, 222), (816, 194), (876, 204), (952, 178)]
    for i in range(len(pts) - 1):
        c.line(pts[i], pts[i + 1], "#2F4B7C", 2)
    for px, py in pts:
        c.d.ellipse([c.px(px - 3), c.px(py - 3), c.px(px + 3), c.px(py + 3)], fill="#2F4B7C")

    # ② 逐回合表
    ui_block(c, 80, 278, 930, 244, 2, "逐回合表")
    cols = [80, 140, 380, 600, 780, 890, 1010]
    heads = ["回合", "局面摘要", "建议", "你的操作", "是否一致", "结果"]
    c.rect(80, 312, 930, 34, fill="#ECEFF1", outline=None)
    for i, h in enumerate(heads):
        c.text(cols[i] + 12, 322, h, fs=13, bold=True, color=U_INK)
    rows = [
        ["1", "HP 68，敌人 12 攻击", "打出【防御】", "打出【防御】", "✓", "HP 60"],
        ["2", "HP 60，敌人 9 攻击", "打出【打击】", "打出【打击】", "✓", "敌人 HP 32"],
        ["3", "HP 42，敌人 11 攻击", "先出【防御】", "打出【打击】", "✗", "HP 31"],
        ["4", "HP 31，敌人残血 11", "打出【打击】斩杀", "打出【打击】", "✓", "胜利"],
    ]
    for r, row in enumerate(rows):
        y = 346 + r * 44
        if r % 2 == 1:
            c.rect(80, y, 930, 44, fill="#FAFAFA", outline=None)
        for i, cell in enumerate(row):
            if cell == "✓":
                ui_tick(c, cols[i] + 22, y + 22, s=9, color="#2E7D32", lw=2.4)
                continue
            if cell == "✗":
                ui_crossmark(c, cols[i] + 22, y + 22, s=9, color=C_WARN, lw=2.6)
                continue
            c.text(cols[i] + 12, y + 14, cell, fs=13, color=U_INK)
        c.line((80, y + 44), (1010, y + 44), "#CFD8DC", 1.2)
    for x in cols[1:-1]:
        c.line((x, 312), (x, 522), "#CFD8DC", 1.2)

    # ③ 关键决策点卡片
    ui_block(c, 80, 534, 930, 206, 3, "关键决策点卡片")
    cards = [
        ("第 3 回合 · 关键决策点", "局面：HP 42，敌人意图 11 攻击", "建议：先出【防御】",
         "依据：下回合有斩杀牌，先保血", "你的操作：打出【打击】（HP 31 → 20）"),
        ("第 1 回合 · 一般决策", "局面：HP 68，敌人 12 攻击", "建议：打出【防御】",
         "依据：先减伤，避免后续被连击", "你的操作：打出【防御】"),
        ("第 4 回合 · 斩杀决策", "局面：敌人残血 11", "建议：打出【打击】斩杀",
         "依据：可直接结束本场战斗", "你的操作：打出【打击】"),
    ]
    for i, cd in enumerate(cards):
        x = 96 + i * 302
        c.rect(x, 568, 290, 156, fill="#FFFFFF", outline="#CFD8DC", r=8, lw=1.4)
        c.text(x + 12, 578, cd[0], fs=13, bold=True, color="#2F4B7C")
        for j, ln in enumerate(cd[1:]):
            c.text(x + 12, 604 + j * 26, ln, fs=12, color=U_INK)

    # ④ 记忆命中
    c.rect(80, 752, 930, 36, fill="#E0F2F1", outline="#00695C", r=8, lw=1.4)
    c.circled(102, 770, 4, r=13, fs=15)
    c.text(126, 762, "本局参考了 7 个历史局面（记忆命中 3 次）", fs=13, color="#00695C")

    # ⑤ 导出与再来一局
    c.rect(80, 798, 930, 40, fill="#FFFFFF", outline="#CFD8DC", r=10, lw=1.4)
    c.circled(102, 818, 5, r=13, fs=15)
    c.text(126, 810, "导出与再来一局", fs=13, bold=True, color=U_INK)
    ui_btn(c, 556, 804, 130, 28, "导出 Markdown", fs=12)
    ui_btn(c, 694, 804, 100, 28, "导出 PDF", fs=12)
    ui_btn(c, 802, 804, 96, 28, "再来一局", fs=12)
    ui_btn(c, 906, 804, 92, 28, "返回首页", fs=12)

    # 右侧：加载与空数据
    c.text(1096, 106, "状态与空数据", fs=15, bold=True, color=U_INK)
    ui_card(c, 1080, 140, 420, 190, "加载中", U_MUTE)
    c.text(1096, 174, "报告生成中…", fs=13, color=U_MUTE)
    ui_bar(c, 1096, 226, 260, 12, 0.7)
    ui_small(c, 1096, 252, "统计逐回合数据与关键决策点")

    ui_card(c, 1080, 354, 420, 200, "空数据", U_MUTE)
    c.text(1096, 388, "本局还没有记录", fs=14, bold=True, color=U_INK)
    c.text(1096, 416, "先完成一次对局，或从首页", fs=13, color=U_MUTE)
    c.text(1096, 438, "“打开最近复盘”进入", fs=13, color=U_MUTE)
    ui_btn(c, 1096, 482, 150, 36, "去开始一局", fs=14)

    ui_legend(c, 50, 872, 1400,
              "① 结果摘要　② 逐回合表（红色叉号标出建议与实际不一致的回合）　③ 关键决策点卡片　"
              "④ 记忆命中提示　⑤ 导出与再来一局；右侧为加载与空数据状态。")
    return c.save("图12-界面原型-复盘报告页.png")


FIGS = {
    "1": fig01,
    "2": fig02,
    "3": fig03,
    "4": fig04,
    "5": fig05,
    "6": fig06,
    "7": fig07,
    "9": fig09,
    "10": fig10,
    "11": fig11,
    "12": fig12,
}


def main(argv):
    keys = list(FIGS) if (not argv or argv[0] == "all") else argv
    for k in keys:
        if k not in FIGS:
            print("skip unknown figure:", k)
            continue
        FIGS[k]()


if __name__ == "__main__":
    main(sys.argv[1:])
