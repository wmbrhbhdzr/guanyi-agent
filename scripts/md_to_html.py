# -*- coding: utf-8 -*-
"""把实验报告 Markdown 转成“适合浏览器打印成 PDF”的 HTML（零依赖）。

只用标准库，支持本课程报告实际用到的语法子集：
    标题（#/##/###）、表格、围栏代码块、图片、粗体、行内代码、链接、
    引用块、有序/无序列表、分隔线；并识别以“图 N”开头的图注段落。

用法：
    .venv\\Scripts\\python.exe scripts\\md_to_html.py 实验4-软件基础功能开发.md
    # 生成同名 .html，用浏览器打开 → Ctrl+P → 另存为 PDF

打印建议：A4、边距默认、勾选“背景图形”、缩放 100%（若表格被裁切降到 80%）。
"""

import html
import re
import sys
from pathlib import Path

CSS = """
@page { size: A4; margin: 15mm 13mm; }
* { box-sizing: border-box; }
body { font-family: "Microsoft YaHei", "微软雅黑", "SimSun", sans-serif;
       font-size: 10.5pt; line-height: 1.65; color: #111; margin: 0 auto; max-width: 860px; padding: 0 4px; }
h1 { font-size: 18pt; text-align: center; margin: 0 0 14px; padding-bottom: 8px; border-bottom: 2px solid #333; }
h2 { font-size: 14pt; margin: 22px 0 8px; padding-left: 8px; border-left: 5px solid #2F4B7C;
     page-break-before: always; page-break-after: avoid; }
h1 + h2, h2:first-of-type { page-break-before: avoid; }
h3 { font-size: 12pt; margin: 16px 0 6px; color: #1a3a5c; page-break-after: avoid; }
p { margin: 6px 0; text-align: justify; }
table { border-collapse: collapse; width: 100%; font-size: 8.8pt; margin: 8px 0; page-break-inside: avoid; }
th, td { border: 1px solid #9aa4b0; padding: 4px 6px; vertical-align: top; }
th { background: #eef2f7; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }
img { max-width: 100%; height: auto; display: block; margin: 8px auto; border: 1px solid #d5d5d5; page-break-inside: avoid; }
p.caption { text-align: center; font-size: 9pt; color: #444; margin: 2px 0 14px; }
pre { background: #f6f8fa; border: 1px solid #d8dee4; border-radius: 3px; padding: 8px 10px;
      font-family: Consolas, "Courier New", monospace; font-size: 8.5pt; line-height: 1.45;
      white-space: pre-wrap; word-break: break-all; page-break-inside: avoid; }
code { font-family: Consolas, "Courier New", monospace; background: #f0f2f5; padding: 0 3px; font-size: 9.2pt; }
pre code { background: none; padding: 0; font-size: inherit; }
blockquote { margin: 8px 0; padding: 6px 12px; border-left: 4px solid #b9c4d0; background: #fafbfc; color: #333; }
blockquote p { margin: 2px 0; }
ul, ol { margin: 6px 0 6px 22px; padding: 0; }
li { margin: 2px 0; }
hr { border: none; border-top: 1px solid #ccc; margin: 14px 0; }
a { color: #1a5fb4; text-decoration: none; }
"""


def inline(text):
    """处理行内语法：先转义，再替换粗体/行内代码/链接。"""
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def convert(md_text):
    lines = md_text.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 围栏代码块
        if stripped.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(block), quote=False))
            continue

        # 表格
        if stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            rows = [[c.strip() for c in r.strip("|").split("|")] for r in block]
            rows = [r for r in rows if not all(set(c) <= set("-: ") for c in r)]   # 去掉分隔行
            if rows:
                out.append("<table>")
                out.append("<thead><tr>%s</tr></thead>" % "".join("<th>%s</th>" % inline(c) for c in rows[0]))
                out.append("<tbody>")
                for r in rows[1:]:
                    out.append("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r))
                out.append("</tbody></table>")
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (level, inline(m.group(2)), level))
            i += 1
            continue

        # 分隔线
        if re.match(r"^-{3,}$", stripped):
            out.append("<hr>")
            i += 1
            continue

        # 图片独占一行
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if m:
            out.append('<img src="%s" alt="%s">' % (m.group(2), html.escape(m.group(1), quote=True)))
            i += 1
            continue

        # 引用块
        if stripped.startswith(">"):
            block = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                block.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote>%s</blockquote>"
                       % "".join("<p>%s</p>" % inline(t) for t in block if t))
            continue

        # 列表
        if re.match(r"^([-*]|\d+\.)\s+", stripped):
            ordered = bool(re.match(r"^\d+\.\s+", stripped))
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(lines) and re.match(r"^([-*]|\d+\.)\s+", lines[i].strip()):
                items.append(re.sub(r"^([-*]|\d+\.)\s+", "", lines[i].strip()))
                i += 1
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(t) for t in items), tag))
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 图注（“图 N　说明”）与普通段落
        cls = ' class="caption"' if re.match(r"^图\s*\d+", stripped) else ""
        out.append("<p%s>%s</p>" % (cls, inline(stripped)))
        i += 1
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        print("用法：python scripts/md_to_html.py <报告.md> [输出.html]")
        return 2
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".html")
    body = convert(src.read_text(encoding="utf-8"))
    title = src.stem
    dst.write_text(
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n%s\n</body>\n</html>\n"
        % (html.escape(title), CSS, body), encoding="utf-8")
    imgs = len(re.findall(r"<img ", body))
    print("已生成 %s（图片 %d 张，表格 %d 个，%d 字节）"
          % (dst, imgs, body.count("<table>"), dst.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
