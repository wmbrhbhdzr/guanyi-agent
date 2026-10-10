# -*- coding: utf-8 -*-
"""规则基线决策器（非 AI）。

它顶替视觉语言模型做出决策，用于两件事：

1. 实验4 的**非 AI 业务闭环**演示——不依赖任何模型服务，闭环也能完整跑通；
2. 实验6 的**规则基线**——评测时要拿它和模型对比，回答“模型是不是真的更好”。

这也是需求说明 §7.4 早已写明的“非 AI 降级方案”：降级后系统仍是完整软件。

规则（可解释、可复核，故意保持简单）：

- 若敌人意图伤害 ≥ 当前血量的 1/3，且手上有“防御” → 先防御保血；
- 否则若敌人剩余血量 ≤ 手上最高单卡伤害 → 出伤害最高的攻击牌（争取斩杀）；
- 否则若手上有“打击” → 出打击压血；
- 都不满足 → 结束回合。
"""

#: 简化的卡牌伤害表（实验4 只用最基础的几张牌，后续可从截图识别替换）
CARD_DAMAGE = {"打击": 6, "重击": 8, "痛击": 8}
CARD_BLOCK = {"防御": 5, "铁斩波": 6}


def decide(state, legal_actions):
    """给定局面与合法动作集，返回建议 dict：{action, reason, confidence}。

    state 字段（都用最朴素的名字，便于界面表单直接填）：
        hp / max_hp / energy / enemy_hp / enemy_intent / hand（手牌名列表）
    """
    state = state or {}
    legal = list(legal_actions or [])
    hand = list(state.get("hand") or [])
    hp = int(state.get("hp", 0) or 0)
    max_hp = int(state.get("max_hp", 80) or 80)
    enemy_hp = int(state.get("enemy_hp", 0) or 0)
    intent = int(state.get("enemy_intent", 0) or 0)

    def make(card, reason, confidence):
        return {
            "action": {"action_type": "play_card", "card_name": card, "energy_cost": 1},
            "reason": reason,
            "confidence": confidence,
        }

    # 规则一：保血
    threatens = intent * 3 >= max(1, hp)
    if threatens and "防御" in hand:
        return make("防御", "敌人意图 %d 点攻击，已接近当前血量的三分之一，先减伤更稳" % intent, 0.78)

    # 规则二：斩杀
    attack_cards = [c for c in hand if c in CARD_DAMAGE]
    if attack_cards:
        best = max(attack_cards, key=lambda c: CARD_DAMAGE[c])
        if enemy_hp and CARD_DAMAGE[best] >= enemy_hp:
            return make(best, "敌人剩余 %d 点血量，【%s】可直接斩杀" % (enemy_hp, best), 0.9)

    # 规则三：压血
    if "打击" in hand:
        return make("打击", "用低费攻击压低敌方血量，保留能量应对后续", 0.72)

    # 兜底：结束回合（若合法动作集里有它）
    if any(a.endswith("end_turn") for a in legal) or not legal:
        return {
            "action": {"action_type": "end_turn"},
            "reason": "手上没有可用的攻击或防御牌，结束回合等待抽牌",
            "confidence": 0.6,
        }

    # 合法动作集里连 end_turn 都没有：如实弃权，不猜
    return {
        "action": None,
        "reason": "合法动作集里没有规则可用的动作，无法给出建议",
        "confidence": 0.0,
    }
