# -*- coding: utf-8 -*-
"""知识库加载与切分（实验5 §2.3）。

切分策略
--------
`knowledge/*.md` 是用 `scripts/build_kb.py` 生成的：**每个 `## ` 标题块就是一条独立知识**
（一张卡、一个状态、一只敌人、一件遗物）。因此切分器按标题切，得到 53 个片段：

- **片段大小**：150–600 字符（一张卡约 250 字符，敌人条目略长）；
- **是否重叠**：不重叠——每个片段本身就是完整、可独立引用的知识单元，
  重叠只会让同一句话被重复检索、并在回答里出现重复引用；
- **资料更新**：重跑 `scripts/build_kb.py` 覆盖生成，片段 id 由「文件名 + 标题」决定，保持稳定。

片段元数据：`chunk_id`、`source_file`、`section`（文件级标题）、`title`、`chars`、`source`（条目里那行来源）。
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

KB_DIR = Path("knowledge")


@dataclass
class Chunk:
    """一个知识片段。"""

    chunk_id: str
    source_file: str
    section: str
    title: str
    text: str
    source: str = ""

    @property
    def chars(self) -> int:
        return len(self.text)

    def to_dict(self) -> Dict:
        return {
            "chunk_id": self.chunk_id,
            "source_file": self.source_file,
            "section": self.section,
            "title": self.title,
            "chars": self.chars,
            "source": self.source,
            "text": self.text,
        }


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_markdown(path: Path, kb_dir: Path = KB_DIR) -> List[Chunk]:
    """把一个 Markdown 文件按 `## ` 标题切成片段。"""
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"<!--.*?-->\s*", "", raw, flags=re.S)          # 去掉生成脚本写的注释头
    section = Path(path).stem
    for line in raw.splitlines():
        if line.startswith("# "):
            section = line[2:].strip()
            break
    blocks = re.split(r"^## ", raw, flags=re.M)[1:]
    chunks = []
    for index, block in enumerate(blocks, start=1):
        title = _norm(block.splitlines()[0]) if block.strip() else "（无标题）"
        body = "## " + block.strip() + "\n"
        src = ""
        for line in body.splitlines():
            if line.startswith("- 来源："):
                src = line[len("- 来源："):].strip()
                break
        chunks.append(Chunk(
            chunk_id="%s#%02d" % (Path(path).stem, index),
            source_file=str(Path(kb_dir.name) / Path(path).name),
            section=section,
            title=title,
            text=body,
            source=src,
        ))
    return chunks


def load_chunks(kb_dir=KB_DIR) -> List[Chunk]:
    """加载知识库全部片段（按文件名排序，保证顺序稳定）。"""
    kb_dir = Path(kb_dir)
    if not kb_dir.exists():
        return []
    chunks: List[Chunk] = []
    for path in sorted(kb_dir.glob("*.md")):
        if path.name.lower().startswith(("sources", "readme")):
            continue
        chunks.extend(load_markdown(path, kb_dir))
    return chunks


def stats(chunks: List[Chunk]) -> Dict:
    """片段规模统计，用于报告 2.3 的“片段大小”说明。"""
    if not chunks:
        return {"count": 0}
    sizes = sorted(c.chars for c in chunks)
    by_section: Dict[str, int] = {}
    for c in chunks:
        by_section[c.section] = by_section.get(c.section, 0) + 1
    return {
        "count": len(chunks),
        "min_chars": sizes[0],
        "median_chars": sizes[len(sizes) // 2],
        "max_chars": sizes[-1],
        "total_chars": sum(sizes),
        "overlap": False,
        "by_section": by_section,
    }
