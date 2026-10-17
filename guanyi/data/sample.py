# -*- coding: utf-8 -*-
"""数据层：样例数据的初始化与清空（讲义 2.2 要求“可重复使用的样例数据”）。

样例是**《杀戮尖塔 2》第一章**的一场战斗：与“劫掠者刺客”交手三个回合，
第 3 回合“建议防御、玩家打出攻击”，因此报告里会出现一个关键决策点。

> 说明（需求说明 V1.2 / C6）：实验4 时期的样例沿用《杀戮尖塔》的敌人名，
> 实验5 起统一改为《杀戮尖塔 2》的敌人（劫掠者刺客，见 knowledge/第一章-敌人.md）。
"""

from ..core.models import DecisionPoint, Run
from .store import JsonlStore

ENEMY = "劫掠者刺客"

#: 三个决策点：前两个建议与实际一致，第 3 个不一致（报告里的关键决策点）
SAMPLE_POINTS = [
    {
        "turn": 1,
        "state_summary": "HP 68/80，能量 3/3，手牌 5 张，敌人 %s HP 23 意图攻击 10" % ENEMY,
        "legal_actions": ["play_card:防御", "play_card:打击", "end_turn"],
        "suggestion_action": {"action_type": "play_card", "card_name": "防御", "energy_cost": 1},
        "suggestion_reason": "敌人意图 10 点攻击，先减伤可避免被连续消耗",
        "confidence": 0.82,
        "player_action": {"action_type": "play_card", "card_name": "防御", "energy_cost": 1},
        "result": {"hp_delta": -5, "note": "HP 68 → 63"},
    },
    {
        "turn": 2,
        "state_summary": "HP 63/80，能量 3/3，手牌 5 张，敌人 %s HP 23 意图攻击 10" % ENEMY,
        "legal_actions": ["play_card:防御", "play_card:打击", "end_turn"],
        "suggestion_action": {"action_type": "play_card", "card_name": "打击", "energy_cost": 1},
        "suggestion_reason": "敌方血量仍高，用低费攻击压血，同时保留能量应对后续",
        "confidence": 0.74,
        "player_action": {"action_type": "play_card", "card_name": "打击", "energy_cost": 1},
        "result": {"hp_delta": -10, "enemy_hp_delta": -6, "note": "敌人 HP 23 → 17，HP 63 → 53"},
    },
    {
        "turn": 3,
        "state_summary": "HP 53/80，能量 2/3，敌人 %s HP 17 意图攻击 10" % ENEMY,
        "legal_actions": ["play_card:防御", "play_card:打击", "end_turn"],
        "suggestion_action": {"action_type": "play_card", "card_name": "防御", "energy_cost": 1},
        "suggestion_reason": "敌方血量已进入斩杀范围，本回合先保血，下回合再收尾更稳",
        "confidence": 0.69,
        "player_action": {"action_type": "play_card", "card_name": "打击", "energy_cost": 1},
        "result": {"hp_delta": -10, "enemy_hp_delta": -6, "note": "HP 53 → 43，敌人 HP 17 → 11"},
    },
]


def seed_sample_run(store: JsonlStore, run_id="run-0001", outcome="胜", seed="GUANYI-DEMO") -> Run:
    """写入一局样例数据，返回该 Run。"""
    run = Run(
        run_id=run_id,
        seed=seed,
        status="finished",
        outcome=outcome,
        config_snapshot={"tier": "仅复盘", "region": "1280x720@(120,80)", "model": "rule-baseline"},
    )
    store.save_run(run)
    for index, raw in enumerate(SAMPLE_POINTS, start=1):
        point = DecisionPoint(
            dp_id="dp-%s-%02d" % (run_id.split("-")[-1], index),
            run_id=run_id,
            turn=raw["turn"],
            seq=index,
            state_summary=raw["state_summary"],
            legal_actions=list(raw["legal_actions"]),
            suggestion_action=raw["suggestion_action"],
            suggestion_reason=raw["suggestion_reason"],
            confidence=raw["confidence"],
            player_action=raw["player_action"],
            guardrail={"verdict": "allow", "reason": "动作在手牌与能量允许范围内", "code": "ok"},
            model_meta={"source": "rule_baseline", "latency_ms": 0, "cost": 0.0},
            result=raw["result"],
        )
        point.is_consistent = point.check_consistency()
        store.append_decision(point)
    return run


def reset(store: JsonlStore) -> int:
    """清空全部运行记录（“恢复出厂”用）。"""
    return store.clear()


def seed_empty_run(store: JsonlStore, run_id="run-empty", outcome=None) -> Run:
    """写入一局**没有任何决策点**的对局，用于空数据场景与测试用例 6。"""
    run = Run(
        run_id=run_id,
        seed="EMPTY",
        status="finished" if outcome else "running",
        outcome=outcome,
        config_snapshot={"tier": "仅复盘"},
    )
    store.save_run(run)
    return run
