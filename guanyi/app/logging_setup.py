# -*- coding: utf-8 -*-
"""日志设置（讲义 2.5：记录能够帮助定位问题的必要日志）。

日志位置：
    data/runs/<run_id>/app.log    单局日志（录入、护栏结论、报告生成、异常）
    data/runs/app.log             不针对具体对局的日志（启动、参数错误等）

格式：`时间 级别 [模块] 消息`，UTF-8 编码，界面与命令行都写同一份。
"""

import logging
from pathlib import Path

_LOGGERS = {}


def get_logger(run_id=None, root="data/runs", console=False):
    """取一个按对局隔离的 logger（同一“目录 + 对局”只会创建一次）。"""
    key = (str(root), run_id or "_global")
    if key in _LOGGERS:
        return _LOGGERS[key]

    logger = logging.getLogger("guanyi.%s.%s" % (key[0].replace("\\", "/"), key[1]))
    logger.setLevel(logging.INFO)
    logger.propagate = False

    path = Path(root) / (run_id if run_id else "")
    path.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path / "app.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(module)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)

    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(stream)

    _LOGGERS[key] = logger
    return logger


def reset_loggers():
    """测试用：关闭并清空已创建的 logger。"""
    for logger in _LOGGERS.values():
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
    _LOGGERS.clear()
