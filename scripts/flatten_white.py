# -*- coding: utf-8 -*-
"""
把带透明通道的 PNG 垫成白底。

背景：StarUML 的 File → Export As → PNG 默认导出**透明背景**，插进报告或图片查看器里
      会显示成"背景是空的"（棋盘格/黑底）。本脚本把透明像素合成到纯白底上，内容不变。

用法：
    .venv\\Scripts\\python.exe scripts\\flatten_white.py                       # 处理 image/实验3-软件架构与界面设计/*.png
    .venv\\Scripts\\python.exe scripts\\flatten_white.py 图片1.png 图片2.png   # 处理指定文件（支持通配符）
"""

import glob
import io
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "image", "实验3-软件架构与界面设计", "*.png")


def flatten(path):
    # 先整块读进内存并关闭文件句柄，避免 Windows 上"边读边写同一文件"出问题
    with open(path, "rb") as fp:
        im = Image.open(io.BytesIO(fp.read()))
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        tmp = os.path.join(ROOT, "scripts", "_flatten_tmp.png")
        bg.save(tmp)
        os.replace(tmp, path)
        print("白底已填充：%s  %dx%d" % (os.path.basename(path), bg.size[0], bg.size[1]))
    else:
        print("本来就是不透明，跳过：%s（mode=%s）" % (os.path.basename(path), im.mode))


def main(argv):
    patterns = argv or [DEFAULT]
    files = []
    for p in patterns:
        hit = glob.glob(p) if any(c in p for c in "*?[") else []
        files.extend(hit or [p])
    if not files:
        print("没有匹配到文件")
        return
    for f in files:
        flatten(f)


if __name__ == "__main__":
    main(sys.argv[1:])
