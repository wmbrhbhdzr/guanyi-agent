# -*- coding: utf-8 -*-
"""数据访问层：把领域对象落到本地文件（对应实验3 图 5 的“保存位置”一列）。

本层实现实验3 定义的 `StoragePort`，上层的应用层与界面只认它暴露的方法。
"""

from .sample import reset, seed_empty_run, seed_sample_run
from .store import JsonlStore

__all__ = ["JsonlStore", "seed_sample_run", "seed_empty_run", "reset"]
