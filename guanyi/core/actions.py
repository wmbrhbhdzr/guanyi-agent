# -*- coding: utf-8 -*-
"""领域层动作校验的公共常量与工具。"""

#: 允许的动作类型（对应实验3 图 5 的 `Action.action_type` 约束）
ALLOWED_ACTION_TYPES = ("play_card", "end_turn", "use_potion")

#: 一局的状态取值
ALLOWED_RUN_STATUS = ("running", "finished", "aborted")

#: 一局的结果取值
ALLOWED_OUTCOMES = ("胜", "负", "中止")


def action_key(action):
    """把动作 dict 归一化成可与合法动作集比较的字符串。

    例：{"action_type": "play_card", "card_name": "防御"} → "play_card:防御"
        {"action_type": "end_turn"}                       → "end_turn"
    """
    if not action:
        return ""
    kind = str(action.get("action_type", "") or "")
    card = str(action.get("card_name", "") or "")
    return "%s:%s" % (kind, card) if card else kind
