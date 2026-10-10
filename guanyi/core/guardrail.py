# -*- coding: utf-8 -*-
"""规则护栏（接口 I-3）：动作合法性校验。

设计原则（实验3 图 1）：**判断权归模型，放行权归规则**。
护栏只做规则能确定的事，遇到不确定就拒绝并说明原因，绝不猜测。
返回的结论是一个值对象：`{"verdict": "allow"|"deny", "reason": ..., "code": ...}`。
"""

from .actions import ALLOWED_ACTION_TYPES, action_key


def check_action(action, legal_actions=None, energy_left=None):
    """校验一个动作是否可以被放行。

    参数：
        action       建议动作 dict，如 {"action_type": "play_card", "card_name": "防御"}
        legal_actions 规则给出的合法动作集（形如 "play_card:防御"、"end_turn"）
        energy_left  本回合剩余能量（None 表示不校验）

    返回：{"verdict", "reason", "code"}
    """
    if not action:
        return {"verdict": "deny", "reason": "没有给出动作，无法放行", "code": "invalid_input"}

    kind = action.get("action_type")
    if kind not in ALLOWED_ACTION_TYPES:
        return {
            "verdict": "deny",
            "reason": "动作类型 %r 不在允许集合 %s 内" % (kind, "／".join(ALLOWED_ACTION_TYPES)),
            "code": "invalid_input",
        }

    if kind != "end_turn":
        cost = action.get("energy_cost")
        if energy_left is not None and cost is not None and int(cost) > int(energy_left):
            return {
                "verdict": "deny",
                "reason": "该动作需要 %s 点能量，本回合只剩 %s 点" % (cost, energy_left),
                "code": "guardrail_trigger",
            }

    legal = list(legal_actions or [])
    if legal and action_key(action) not in legal:
        return {
            "verdict": "deny",
            "reason": "动作 %s 不在本回合的合法动作集内，已按规则处理" % action_key(action),
            "code": "guardrail_trigger",
        }

    return {"verdict": "allow", "reason": "动作在手牌与能量允许范围内", "code": "ok"}
