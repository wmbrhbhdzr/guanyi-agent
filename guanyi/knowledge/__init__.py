# -*- coding: utf-8 -*-
"""知识库层（实验5）：资料切分（§2.3）与检索（§2.4）。

对应实验3 设计里新增的**知识检索**能力（端口 I-9）。本层只处理“通用游戏知识”，
不含任何对局数据、截图或玩家信息——这是本项目“真值隔离”边界的一部分。
"""

from .retriever import Retriever, search, tokenize
from .splitter import Chunk, load_chunks, stats

__all__ = ["Chunk", "load_chunks", "stats", "Retriever", "search", "tokenize"]
