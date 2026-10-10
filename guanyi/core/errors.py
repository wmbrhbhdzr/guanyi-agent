# -*- coding: utf-8 -*-
"""统一错误码与异常。

对应实验3 报告 3.4.2 的错误码表：每个异常都带 `code`（给日志与程序判断）
与中文 `message`（直接显示给玩家，符合“失败信息为人类可读中文”的可用性需求）。
"""


class GuanyiError(Exception):
    """业务异常基类。"""

    code = "error"
    zh = "发生未知错误"

    def __init__(self, message=None, **details):
        self.message = message or self.zh
        self.details = details
        super().__init__(self.message)

    def to_dict(self):
        return {"code": self.code, "message": self.message, "details": self.details}


class ValidationError(GuanyiError):
    """输入不合法（缺字段、类型不对、取值越界）。"""

    code = "invalid_input"
    zh = "输入格式不正确"


class NotFoundError(GuanyiError):
    """要读取的对局或记录不存在。"""

    code = "not_found"
    zh = "找不到对应的数据"


class DuplicateError(GuanyiError):
    """同一条记录被重复写入。"""

    code = "duplicate_record"
    zh = "记录已存在，未重复写入"


class StorageError(GuanyiError):
    """磁盘读写失败：文件损坏、权限不足、磁盘满等。"""

    code = "storage_error"
    zh = "运行记录读写失败"


class GuardrailDenied(GuanyiError):
    """规则护栏拦截了动作（冲突时以规则为准）。"""

    code = "guardrail_trigger"
    zh = "建议与规则冲突，已按规则处理"


#: 错误码 → 界面中文提示（实验3 报告 3.5.3 的状态表）
ZH_MESSAGES = {
    "invalid_input": "输入格式不正确，请检查后重试",
    "not_found": "找不到这条记录，可能已被清理",
    "duplicate_record": "这条记录已经存在，已跳过重复写入",
    "storage_error": "运行记录读写失败，请检查磁盘或权限",
    "guardrail_trigger": "建议与规则冲突，已按规则处理，请确认",
    "unknown": "发生未知错误",
}


def zh_message(code):
    """把错误码翻译成界面提示文字。"""
    return ZH_MESSAGES.get(code, ZH_MESSAGES["unknown"])
